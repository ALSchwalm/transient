from transient import qemu
import signal


def test_qemu_terminate():
    class StalledQemuRunner(qemu.QemuRunner):
        def _make_command_line(self):
            return ["sleep", "100000"]

    runner = StalledQemuRunner([])
    runner.start()
    assert runner.is_running()
    runner.terminate()
    runner.wait(timeout=10)
    assert runner.returncode() == -signal.SIGTERM


def test_qemu_terminate_kill_after():
    class StalledQemuRunner(qemu.QemuRunner):
        def _make_command_line(self):
            return ["sleep", "100000"]

        @staticmethod
        def _qemu_preexec():
            # dispositions of ignored signals are inherited across exec
            signal.signal(signal.SIGTERM, signal.SIG_IGN)

    runner = StalledQemuRunner([])
    runner.start()
    assert runner.is_running()
    runner.terminate()
    assert runner.is_running()
    runner.terminate(kill_after=1)
    assert runner.returncode() == -signal.SIGKILL
