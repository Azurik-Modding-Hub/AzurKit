//Serve this headless session's program, read-only, over the stock GhydraMCP HTTP API
//on <port> until <stopFile> exists, the run is cancelled or <maxSeconds> pass (0: no
//limit). `python -m devkit re ghidra-serve` runs it on a COPY of a Ghidra project
//(analyzeHeadless <copy> -process <program> -noanalysis -readOnly), never on the owner's.
//Args: <port> <stopFile> <readyFile> <maxSeconds>
//- The program is marked temporary, so HTTP writes change only the in-memory program
//  and POST /program/save or /programs/save has nothing to save. -readOnly alone is not
//  enough: it only skips the save at exit (AZ-193).
//- It registers the stock resources GhydraPlugin does, except ScriptResource and
//  DevResource (arbitrary Java) and UiResource (there is no UI). The listening address
//  comes from -Dghidra.mcp.bind.host, which ghidra-serve sets to 127.0.0.1.
//- <readyFile> is written atomically once the server listens, and again whenever the
//  program's modification number changes, so `ghidra-serve status` can tell a clean
//  serve from one that holds in-memory edits.
//@category Azurik
import ghidra.app.script.GhidraScript;
import ghidra.app.services.ProgramManager;
import ghidra.framework.model.Project;
import ghidra.framework.plugintool.PluginTool;
import ghidra.program.model.listing.Program;
import eu.starsong.ghidra.resource.*;
import eu.starsong.ghidra.server.GhydraServer;
import eu.starsong.ghidra.service.DecompilerService;
import eu.starsong.ghidra.service.FunctionService;
import eu.starsong.ghidra.service.ScalarService;
import eu.starsong.ghidra.service.VariableService;
import java.io.File;
import java.lang.reflect.Proxy;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.HashMap;

public class AzurikServe extends GhidraScript {

	/** The two things the stock resources ask a PluginTool for. */
	static class HeadlessTool extends PluginTool {
		private final ProgramManager pm;
		private final Project project;

		HeadlessTool(ProgramManager pm, Project project) {
			super();
			this.pm = pm;
			this.project = project;
		}

		@Override
		public <T> T getService(Class<T> c) {
			return c == ProgramManager.class ? c.cast(pm) : null;
		}

		@Override
		public Project getProject() {
			return project;
		}
	}

	@Override
	protected void run() throws Exception {
		String[] a = getScriptArgs();
		if (a.length != 4) {
			throw new IllegalArgumentException("args: <port> <stopFile> <readyFile> <maxSeconds>");
		}
		int port = Integer.parseInt(a[0]);
		File stop = new File(a[1]);
		Path ready = new File(a[2]).toPath();
		long maxSeconds = Long.parseLong(a[3]);
		long deadline = maxSeconds > 0 ? System.currentTimeMillis() + maxSeconds * 1000 : Long.MAX_VALUE;
		Program prog = currentProgram;
		if (prog == null) {
			throw new IllegalStateException("no program: run analyzeHeadless with -process <name>");
		}
		// GhidraScript holds one transaction around run(): end it, so each HTTP write
		// commits on its own and one failed request can't roll back the others.
		end(true);
		prog.setTemporary(true); // nothing to save, whatever a save route is asked

		ProgramManager pm = (ProgramManager) Proxy.newProxyInstance(
			ProgramManager.class.getClassLoader(), new Class<?>[] { ProgramManager.class },
			(self, m, args) -> switch (m.getName()) {
				case "getCurrentProgram", "getProgram" -> prog;
				case "getAllOpenPrograms" -> new Program[] { prog };
				case "isVisible" -> Boolean.TRUE;
				case "hashCode" -> System.identityHashCode(self);
				case "equals" -> self == args[0];
				case "toString" -> "AzurikServeProgramManager";
				default -> throw new UnsupportedOperationException("headless serve: " + m.getName());
			});
		GhydraServer server = new GhydraServer(new HeadlessTool(pm, state.getProject()), port,
			new HashMap<>(), false);
		FunctionService fs = new FunctionService();
		DecompilerService ds = new DecompilerService(fs);
		server.register(new RootResource(false), new FunctionResource(fs, ds), new SymbolResource(),
			new DataResource(), new MemoryResource(), new SegmentResource(), new XrefResource(),
			new ProgramResource(), new InstanceResource(), new AnalysisResource(), new StructResource(),
			new DataTypeResource(), new ScalarResource(new ScalarService()),
			new VariableResource(new VariableService(ds)), new ClassResource(), new NamespaceResource(),
			new ProjectResource());
		server.start();
		long readyNumber = prog.getModificationNumber();
		long written = readyNumber;
		writeReady(ready, port, prog, readyNumber, readyNumber);
		println("AZSERVE: serving a read-only copy of " + prog.getName() + " on port " + port);
		String why = "maxSeconds";
		try {
			while (System.currentTimeMillis() < deadline) {
				if (stop.exists() || monitor.isCancelled()) {
					why = stop.exists() ? "stop file" : "cancelled";
					break;
				}
				long now = prog.getModificationNumber();
				if (now != written) {
					writeReady(ready, port, prog, readyNumber, now);
					written = now;
				}
				Thread.sleep(250);
			}
		}
		finally {
			server.stop();
			println("AZSERVE: stopped (" + why + "); in-memory edits: "
				+ (prog.getModificationNumber() != readyNumber) + "; unsaved changes: " + prog.isChanged());
		}
	}

	private static void writeReady(Path ready, int port, Program prog, long readyNumber, long now)
			throws Exception {
		String json = String.format(
			"{\"port\": %d, \"program\": \"%s\", \"pid\": %d, \"readyModificationNumber\": %d, "
				+ "\"modificationNumber\": %d}%n",
			port, prog.getName().replace("\\", "\\\\").replace("\"", "\\\""),
			ProcessHandle.current().pid(), readyNumber, now);
		Path tmp = ready.resolveSibling(ready.getFileName() + ".tmp");
		Files.writeString(tmp, json, StandardCharsets.UTF_8);
		Files.move(tmp, ready, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
	}
}
