//Apply, dry-run or verify a reviewed edit plan on this headless session's program.
//`python -m devkit re ghidra-apply` runs it (D90): dry on a copy (-readOnly), apply on the closed
//project, verify on a copy of the result (-readOnly). Never through the GUI or scripts_run.
//Args: <dry|apply|verify> <plan.json>
//The plan is a JSON list of lines, each one object:
//  {"op": "rename", "va": "0x88A80", "from": "<current name>", "to": "<new name>"}
//  {"op": "rename_label", "va": "0x37BE98", "from": "<current name>", "to": "<new name>"}
//  {"op": "comment", "va": "0x88A80", "kind": "plate|pre|eol|post|repeatable", "text": "..."}
//  {"op": "delete_equate", "name": "AZURIK_SMOKETEST_ONE"}
//  {"op": "delete_category", "path": "/AzurikSmokeTest"}
//  {"op": "create_function", "va": "0x42750"[, "name": "<name>"]}
//- Every line is validated before anything changes; a line already in effect is skipped.
//- rename takes a function; rename_label the primary symbol at va when it is not one
//  (a label), keeping its namespace.
//- create_function disassembles from va (following its flow) and makes a function there,
//  with Ghidra's default name unless the line names one. It refuses a va inside another
//  function or instruction, on defined data, or whose bytes don't decode.
//- A pending delete_category names what Ghidra clears with its types: the data, the
//  functions (signature or variables) and the other types that use them.
//- apply: every pending line in one transaction, then every line checked in memory; any
//  error rolls the whole transaction back and fails the run.
//- Markers (ghidra-apply reads these, never the exit code, which is 0 even when a script
//  throws): "AZPLAN: pending|in effect <line>", then "AZPLAN: DRY n of m pending",
//  "AZPLAN: APPLIED n of m" or "AZPLAN: ROLLED BACK", and "AZVERIFY: OK|FAIL". Names and
//  texts are printed JSON-quoted, so no plan text can forge a marker line.
//@category Azurik
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import ghidra.app.cmd.function.CreateFunctionCmd;
import ghidra.app.script.GhidraScript;
import ghidra.app.util.PseudoDisassembler;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.Array;
import ghidra.program.model.data.Category;
import ghidra.program.model.data.CategoryPath;
import ghidra.program.model.data.Composite;
import ghidra.program.model.data.DataType;
import ghidra.program.model.data.DataTypeComponent;
import ghidra.program.model.data.FunctionDefinition;
import ghidra.program.model.data.ParameterDefinition;
import ghidra.program.model.data.Pointer;
import ghidra.program.model.data.TypeDef;
import ghidra.program.model.listing.CodeUnit;
import ghidra.program.model.listing.CommentType;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.Variable;
import ghidra.program.model.symbol.Equate;
import ghidra.program.model.symbol.SourceType;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolType;
import ghidra.program.model.symbol.SymbolUtilities;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

public class ApplyPlan extends GhidraScript {

	private static final Map<String, Set<String>> KEYS = Map.of(
		"rename", Set.of("op", "va", "from", "to"),
		"rename_label", Set.of("op", "va", "from", "to"),
		"comment", Set.of("op", "va", "kind", "text"),
		"delete_equate", Set.of("op", "name"),
		"delete_category", Set.of("op", "path"),
		"create_function", Set.of("op", "va", "name")); // "name" may be left out
	private static final Gson QUOTE = new GsonBuilder().disableHtmlEscaping().create();

	private static String q(String s) {
		return QUOTE.toJson(s);
	}

	private static String str(JsonObject line, String key) {
		JsonElement e = line.get(key);
		if (e == null || !e.isJsonPrimitive() || !e.getAsJsonPrimitive().isString() || e.getAsString().isEmpty()) {
			throw new IllegalArgumentException("\"" + key + "\" must be a non-empty string");
		}
		return e.getAsString();
	}

	private Address va(JsonObject line) {
		String s = str(line, "va");
		Address a;
		try {
			a = toAddr(Long.decode(s));
		}
		catch (NumberFormatException e) {
			a = null;
		}
		if (a == null || !currentProgram.getMemory().contains(a)) {
			throw new IllegalArgumentException("va " + s + " is not in the program's memory");
		}
		return a;
	}

	/** Validates the line; null when it is already in effect, else what applying it changes. */
	private String pending(JsonObject line) throws Exception {
		String op = str(line, "op");
		if (!KEYS.containsKey(op)) {
			throw new IllegalArgumentException("unknown op " + q(op) + " (one of " + KEYS.keySet() + ")");
		}
		Set<String> keys = op.equals("create_function") && !line.has("name")
			? Set.of("op", "va") : KEYS.get(op);
		if (!line.keySet().equals(keys)) {
			throw new IllegalArgumentException(op + " takes exactly the keys " + KEYS.get(op)
				+ (op.equals("create_function") ? " (\"name\" may be left out)" : ""));
		}
		switch (op) {
			case "rename": {
				Address a = va(line);
				String from = str(line, "from"), to = str(line, "to");
				SymbolUtilities.validateName(to);
				Function f = getFunctionAt(a);
				if (f == null) {
					throw new IllegalArgumentException("no function starts at " + a);
				}
				if (f.getName().equals(to)) {
					return null;
				}
				if (!f.getName().equals(from)) {
					throw new IllegalArgumentException("the function at " + a + " is " + q(f.getName())
						+ ", not the expected " + q(from));
				}
				return "rename " + a + " " + q(from) + " -> " + q(to);
			}
			case "rename_label": {
				Address a = va(line);
				String from = str(line, "from"), to = str(line, "to");
				SymbolUtilities.validateName(to);
				Symbol s = currentProgram.getSymbolTable().getPrimarySymbol(a);
				if (s == null) {
					throw new IllegalArgumentException("no symbol at " + a);
				}
				if (s.getSymbolType() == SymbolType.FUNCTION) {
					throw new IllegalArgumentException("the symbol at " + a + " is the function " + q(s.getName())
						+ ": use rename");
				}
				if (s.getName().equals(to)) {
					return null;
				}
				if (!s.getName().equals(from)) {
					throw new IllegalArgumentException("the label at " + a + " is " + q(s.getName())
						+ ", not the expected " + q(from));
				}
				return "rename_label " + a + " " + q(from) + " -> " + q(to);
			}
			case "comment": {
				Address a = va(line);
				String kind = str(line, "kind"), text = str(line, "text");
				CommentType type;
				try {
					type = CommentType.valueOf(kind.toUpperCase(Locale.ROOT));
				}
				catch (IllegalArgumentException e) {
					throw new IllegalArgumentException("comment kind " + q(kind)
						+ " is not plate, pre, eol, post or repeatable");
				}
				String now = currentProgram.getListing().getComment(type, a);
				if (text.equals(now)) {
					return null;
				}
				return "comment " + a + " " + kind + " " + q(text) + (now == null ? " (none before)"
					: " replaces " + now.length() + " chars: " + q(now));
			}
			case "create_function": {
				Address a = va(line);
				String name = line.has("name") ? str(line, "name") : null;
				if (name != null) {
					SymbolUtilities.validateName(name);
				}
				Function f = getFunctionAt(a);
				if (f != null) {
					if (name == null || f.getName().equals(name)) {
						return null;
					}
					throw new IllegalArgumentException("the function " + q(f.getName()) + " starts at " + a
						+ ": use rename");
				}
				Function holder = getFunctionContaining(a);
				if (holder != null) {
					throw new IllegalArgumentException(a + " is inside the function " + q(holder.getName())
						+ " at " + holder.getEntryPoint());
				}
				CodeUnit cu = currentProgram.getListing().getCodeUnitContaining(a);
				if (cu instanceof Data d && d.isDefined()) {
					throw new IllegalArgumentException(a + " is defined data (" + d.getDataType().getName() + ")");
				}
				if (cu instanceof Instruction && !cu.getMinAddress().equals(a)) {
					throw new IllegalArgumentException(a + " is inside the instruction at " + cu.getMinAddress());
				}
				if (!(cu instanceof Instruction)) {
					try {
						new PseudoDisassembler(currentProgram).disassemble(a);
					}
					catch (Exception e) {
						throw new IllegalArgumentException("the bytes at " + a + " don't decode: " + e.getMessage());
					}
				}
				return "create_function " + a + (name == null ? " (Ghidra's default name)" : " " + q(name))
					+ (cu instanceof Instruction ? ", code there" : ", not code yet");
			}
			case "delete_equate": {
				Equate e = currentProgram.getEquateTable().getEquate(str(line, "name"));
				return e == null ? null : "delete_equate " + q(e.getName()) + " = 0x"
					+ Long.toHexString(e.getValue()) + " (" + e.getReferenceCount() + " references)";
			}
			default: { // delete_category
				String path = str(line, "path");
				if (!path.startsWith("/") || path.equals("/")) {
					throw new IllegalArgumentException("category path " + q(path) + " must be /<name>[/...]");
				}
				Category c = currentProgram.getDataTypeManager().getCategory(new CategoryPath(path));
				if (c == null) {
					return null;
				}
				int[] n = new int[2];
				count(c, n);
				return "delete_category " + q(path) + " (" + n[0] + " types, " + n[1] + " subcategories; "
					+ uses(c.getCategoryPath()) + ")";
			}
		}
	}

	/** Whether dt is a type under cat, or a pointer, an array or a typedef of one. */
	private static boolean under(DataType dt, CategoryPath cat) {
		for (; dt != null; dt = dt instanceof Pointer p ? p.getDataType() : dt instanceof Array a
				? a.getDataType() : dt instanceof TypeDef t ? t.getDataType() : null) {
			if (dt.getCategoryPath().isAncestorOrSelf(cat)) {
				return true;
			}
		}
		return false;
	}

	/** What uses the types under cat, and so loses them when it goes. */
	private String uses(CategoryPath cat) {
		int data = 0, functions = 0, types = 0;
		for (Data d : currentProgram.getListing().getDefinedData(true)) {
			data += under(d.getDataType(), cat) ? 1 : 0;
		}
		for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
			boolean used = under(f.getReturnType(), cat);
			for (Variable v : f.getAllVariables()) {
				used |= under(v.getDataType(), cat);
			}
			functions += used ? 1 : 0;
		}
		for (Iterator<DataType> it = currentProgram.getDataTypeManager().getAllDataTypes(); it.hasNext();) {
			DataType dt = it.next();
			if (dt.getCategoryPath().isAncestorOrSelf(cat)) {
				continue; // goes with the category
			}
			boolean used = under(dt, cat);
			if (dt instanceof Composite c) {
				for (DataTypeComponent m : c.getDefinedComponents()) {
					used |= under(m.getDataType(), cat);
				}
			}
			else if (dt instanceof FunctionDefinition fd) {
				used |= under(fd.getReturnType(), cat);
				for (ParameterDefinition arg : fd.getArguments()) {
					used |= under(arg.getDataType(), cat);
				}
			}
			types += used ? 1 : 0;
		}
		return "used by " + data + " data, " + functions + " functions, " + types + " other types";
	}

	private static void count(Category c, int[] n) {
		n[0] += c.getDataTypes().length;
		for (Category sub : c.getCategories()) {
			n[1]++;
			count(sub, n);
		}
	}

	private void apply(JsonObject line) throws Exception {
		switch (str(line, "op")) {
			case "rename" -> getFunctionAt(va(line)).setName(str(line, "to"), SourceType.USER_DEFINED);
			case "rename_label" -> currentProgram.getSymbolTable().getPrimarySymbol(va(line))
				.setName(str(line, "to"), SourceType.USER_DEFINED);
			case "comment" -> currentProgram.getListing().setComment(va(line),
				CommentType.valueOf(str(line, "kind").toUpperCase(Locale.ROOT)), str(line, "text"));
			case "create_function" -> {
				Address a = va(line);
				disassemble(a);
				if (currentProgram.getListing().getInstructionAt(a) == null) {
					throw new IllegalStateException("could not disassemble at " + a);
				}
				String name = line.has("name") ? str(line, "name") : null;
				CreateFunctionCmd cmd = new CreateFunctionCmd(name, a, null,
					name == null ? SourceType.DEFAULT : SourceType.USER_DEFINED);
				if (!cmd.applyTo(currentProgram, monitor)) {
					throw new IllegalStateException("could not create a function at " + a + ": " + cmd.getStatusMsg());
				}
			}
			case "delete_equate" -> {
				if (!currentProgram.getEquateTable().removeEquate(str(line, "name"))) {
					throw new IllegalStateException("could not delete equate " + q(str(line, "name")));
				}
			}
			default -> {
				CategoryPath p = new CategoryPath(str(line, "path"));
				Category parent = currentProgram.getDataTypeManager().getCategory(p.getParent());
				if (parent == null || !parent.removeCategory(p.getName(), monitor)) {
					throw new IllegalStateException("could not delete category " + q(p.getPath()));
				}
			}
		}
	}

	@Override
	protected void run() throws Exception {
		String[] a = getScriptArgs();
		if (a.length != 2 || !List.of("dry", "apply", "verify").contains(a[0])) {
			throw new IllegalArgumentException("args: <dry|apply|verify> <plan.json>");
		}
		String mode = a[0];
		JsonElement root = JsonParser.parseString(Files.readString(Path.of(a[1]), StandardCharsets.UTF_8));
		if (!root.isJsonArray() || root.getAsJsonArray().isEmpty()) {
			throw new IllegalArgumentException("the plan must be a non-empty JSON list of lines");
		}
		List<JsonObject> plan = new ArrayList<>();
		for (JsonElement e : root.getAsJsonArray()) {
			if (!e.isJsonObject()) {
				throw new IllegalArgumentException("plan line " + (plan.size() + 1) + " is not an object");
			}
			plan.add(e.getAsJsonObject());
		}
		int todo = 0;
		for (int i = 0; i < plan.size(); i++) { // validates every line before anything changes
			String p;
			try {
				p = pending(plan.get(i));
			}
			catch (Exception e) {
				throw new IllegalArgumentException("plan line " + (i + 1) + ": " + e.getMessage(), e);
			}
			todo += p == null ? 0 : 1;
			println("AZPLAN: " + (p == null ? "in effect " + plan.get(i) : "pending " + p));
		}
		if (mode.equals("dry")) {
			println("AZPLAN: DRY " + todo + " of " + plan.size() + " pending");
			return;
		}
		if (mode.equals("verify")) {
			println(todo == 0 ? "AZVERIFY: OK " + plan.size() + " lines in effect"
				: "AZVERIFY: FAIL " + todo + " of " + plan.size() + " lines not in effect");
			return;
		}
		// GhidraScript holds one transaction around run() and commits it even when run()
		// throws: end it, so this one is the outermost and a rollback is a rollback.
		end(true);
		int tx = currentProgram.startTransaction("ApplyPlan");
		boolean ok = false;
		try {
			for (JsonObject line : plan) {
				if (pending(line) != null) {
					apply(line);
				}
			}
			for (int i = 0; i < plan.size(); i++) {
				if (pending(plan.get(i)) != null) {
					throw new IllegalStateException("plan line " + (i + 1) + " is not in effect after the apply");
				}
			}
			ok = true;
		}
		finally {
			currentProgram.endTransaction(tx, ok);
			println(ok ? "AZPLAN: APPLIED " + todo + " of " + plan.size() : "AZPLAN: ROLLED BACK");
		}
	}
}
