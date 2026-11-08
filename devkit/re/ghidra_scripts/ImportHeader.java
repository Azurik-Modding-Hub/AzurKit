//Parse C declarations into the program's data types, filed directly under one category
//(AZ-036): the parser files a header's types under /<file>.h/ (function
//signatures in functions/, #define enums in defines/); this drops that per-file segment, so
///Cat/T and /Cat/functions/F, never /Cat/<file>.h/T. Re-importing the same declarations keeps
//the types already there. A missing header, a parse error (preprocessor or C), or a different
//type of the same name already in place fails the run with nothing imported.
//Args: <category> <header.h path | inline C text> [-I<include dir>]... [-D<NAME=value>]...
//Run it through GhydraMCP's stock scripts_run(source=<this file>, args=[...]) or headless -postScript.
//@category Azurik
import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Set;

import ghidra.app.script.GhidraScript;
import ghidra.app.util.cparser.C.CParserUtils;
import ghidra.program.model.data.Array;
import ghidra.program.model.data.BuiltInDataType;
import ghidra.program.model.data.Category;
import ghidra.program.model.data.CategoryPath;
import ghidra.program.model.data.Composite;
import ghidra.program.model.data.DataType;
import ghidra.program.model.data.DataTypeComponent;
import ghidra.program.model.data.DataTypeManager;
import ghidra.program.model.data.Enum;
import ghidra.program.model.data.FunctionDefinition;
import ghidra.program.model.data.Pointer;
import ghidra.program.model.data.TypeDef;

public class ImportHeader extends GhidraScript {

	@Override
	protected void run() throws Exception {
		String[] a = getScriptArgs();
		if (a.length < 2) {
			throw new IllegalArgumentException(
				"args: <category> <header.h | C text> [-I<dir>]... [-D<NAME=value>]...");
		}
		CategoryPath dest = new CategoryPath(a[0]); // must start with '/'
		List<String> includes = new ArrayList<>();
		List<String> defines = new ArrayList<>();
		for (int i = 2; i < a.length; i++) {
			if (a[i].startsWith("-I")) {
				includes.add(a[i].substring(2));
			}
			else if (a[i].startsWith("-D")) {
				defines.add(a[i]);
			}
			else {
				throw new IllegalArgumentException("not -I<dir> or -D<NAME=value>: " + a[i]);
			}
		}
		DataTypeManager dtm = currentProgram.getDataTypeManager();
		Set<String> before = new HashSet<>();
		declared(dtm).forEach(dt -> before.add(dt.getPathName()));
		Set<CategoryPath> touched = new HashSet<>();
		List<String> imported = new ArrayList<>();
		File header = new File(a[1]);
		if (!header.isFile() && a[1].endsWith(".h")) { // a mistyped path, not inline C
			throw new IllegalArgumentException("no such header: " + a[1]);
		}
		Path inline = header.isFile() ? null : Files.createTempDirectory("azurik-header-");
		try {
			if (inline != null) { // the parser reads files only
				header = Files.writeString(inline.resolve("inline.h"), a[1]).toFile();
			}
			CParserUtils.CParseResults r = CParserUtils.parseHeaderFiles(null,
				new String[] { header.getPath() }, includes.toArray(String[]::new),
				defines.toArray(String[]::new), dtm, monitor);
			for (String m : new String[] { r.cppParseMessages(), r.cParseMessages() }) {
				if (m != null && !m.isBlank()) {
					println(m.strip());
				}
			}
			if (!r.successful()) { // a preprocessor error comes back here, not as an exception
				throw new IllegalArgumentException("parse failed; nothing imported");
			}
			List<DataType> fresh = fresh(dtm, before);
			Map<String, String> planned = new HashMap<>(); // destination path -> shape
			for (DataType dt : fresh) { // check every clash before moving anything
				String path = to(dest, dt).extend(dt.getName()).getPath();
				DataType there = dtm.getDataType(to(dest, dt), dt.getName());
				String want = there == null || there == dt ? planned.get(path) : shape(there);
				if (want != null && !want.equals(shape(dt))) {
					throw new IllegalArgumentException(path + " already exists and differs; nothing imported");
				}
				planned.put(path, shape(dt));
			}
			for (DataType dt : fresh) {
				CategoryPath to = to(dest, dt);
				touched.add(dt.getCategoryPath());
				imported.add(to.extend(dt.getName()).getPath());
				DataType there = dtm.getDataType(to, dt.getName());
				if (there == null) {
					dt.setCategoryPath(to);
				}
				else if (there != dt) {
					dtm.replaceDataType(dt, there, false); // a re-import: keep the type already there
				}
			}
		}
		catch (Exception e) { // a GhidraScript commits even when run() throws: undo first
			List<DataType> fresh = fresh(dtm, before);
			fresh.forEach(dt -> touched.add(dt.getCategoryPath()));
			dtm.remove(fresh, monitor);
			removeEmpty(dtm, touched);
			throw e;
		}
		finally {
			if (inline != null) {
				Files.deleteIfExists(inline.resolve("inline.h"));
				Files.delete(inline);
			}
		}
		removeEmpty(dtm, touched);
		println(imported.size() + " data types under " + dest.getPath() + ": " +
			String.join(", ", imported.subList(0, Math.min(100, imported.size()))) +
			(imported.size() > 100 ? ", …" : ""));
	}

	/** Declared types only: Ghidra adds pointers and arrays on demand while it resolves them. */
	private static List<DataType> declared(DataTypeManager dtm) {
		List<DataType> out = new ArrayList<>();
		for (Iterator<DataType> it = dtm.getAllDataTypes(); it.hasNext();) {
			DataType dt = it.next();
			if (!(dt instanceof Pointer || dt instanceof Array || dt instanceof BuiltInDataType)) {
				out.add(dt);
			}
		}
		return out;
	}

	private static List<DataType> fresh(DataTypeManager dtm, Set<String> before) {
		return declared(dtm).stream().filter(dt -> !before.contains(dt.getPathName())).toList();
	}

	/** Where a parsed type goes: its category with the parser's per-file segment dropped. */
	private static CategoryPath to(CategoryPath dest, DataType dt) {
		List<String> parsed = dt.getCategoryPath().asList();
		return parsed.size() <= 1 ? dest : new CategoryPath(dest, parsed.subList(1, parsed.size()));
	}

	/** A declaration, ignoring categories (isEquivalent compares pointed-to structs by path). */
	private static String shape(DataType dt) {
		StringBuilder s = new StringBuilder(dt.getClass().getSimpleName() + " " + dt.getName() +
			" " + dt.getLength());
		if (dt instanceof Composite c) {
			for (DataTypeComponent d : c.getComponents()) {
				s.append("; ").append(d.getOffset()).append(' ').append(d.getFieldName()).append(' ')
						.append(d.getDataType().getDisplayName()).append(' ').append(d.getLength());
			}
		}
		else if (dt instanceof TypeDef t) {
			s.append(" = ").append(t.getDataType().getDisplayName());
		}
		else if (dt instanceof FunctionDefinition f) {
			s.append(' ').append(f.getPrototypeString());
		}
		else if (dt instanceof Enum e) {
			for (String n : e.getNames()) {
				s.append("; ").append(n).append('=').append(e.getValue(n));
			}
		}
		return s.toString();
	}

	/** Drop each category (and its parents) this run left empty: /inline.h, /foo.h/functions. */
	private void removeEmpty(DataTypeManager dtm, Set<CategoryPath> paths) {
		for (CategoryPath p : paths) {
			for (; !p.isRoot(); p = p.getParent()) {
				Category c = dtm.getCategory(p);
				if (c == null || !c.getParent().removeEmptyCategory(c.getName(), monitor)) {
					break;
				}
			}
		}
	}
}
