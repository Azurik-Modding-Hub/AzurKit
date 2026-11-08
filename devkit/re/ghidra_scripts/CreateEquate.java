//Name a constant in one instruction operand (an equate). Without a value it names the
//scalar the operand already holds, and fails when the operand holds none.
//Args: <address> <operand index> <NAME> [value]
//Run it through GhydraMCP's stock scripts_run(source=<this file>, args=[...]) or headless -postScript.
//@category Azurik
import ghidra.app.cmd.equate.SetEquateCmd;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.scalar.Scalar;

public class CreateEquate extends GhidraScript {

	@Override
	protected void run() throws Exception {
		String[] a = getScriptArgs();
		if (a.length != 3 && a.length != 4) {
			throw new IllegalArgumentException("args: <address> <operand index> <NAME> [value]");
		}
		Address at = toAddr(a[0]);
		Instruction insn = at == null ? null : getInstructionAt(at);
		if (insn == null) {
			throw new IllegalArgumentException("no instruction at " + a[0]);
		}
		int op = Integer.parseInt(a[1]);
		long value = a.length == 4 ? Long.decode(a[3]) : scalar(insn, op);
		SetEquateCmd cmd = new SetEquateCmd(a[2], at, op, value);
		if (!cmd.applyTo(currentProgram)) {
			throw new IllegalArgumentException(cmd.getStatusMsg());
		}
		println("equate " + a[2] + " = 0x" + Long.toHexString(value) + " at " + at + " operand " + op);
	}

	private static long scalar(Instruction insn, int op) {
		Scalar s = op >= 0 && op < insn.getNumOperands() ? insn.getScalar(op) : null;
		if (s == null && op >= 0 && op < insn.getNumOperands()) { // e.g. the 0x10 of [EBX + 0x10]
			for (Object o : insn.getOpObjects(op)) {
				if (o instanceof Scalar found) {
					s = found;
					break;
				}
			}
		}
		if (s == null) {
			throw new IllegalArgumentException("operand " + op + " at " + insn.getAddress() +
				" holds no constant; pass the value");
		}
		return s.getValue();
	}
}
