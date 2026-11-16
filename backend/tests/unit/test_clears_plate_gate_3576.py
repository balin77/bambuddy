"""finish_needs_plate_confirmation with a job that clears its own plate (#3576)."""

import itertools

import pytest

from backend.app.services.print_scheduler import PrintScheduler, finish_needs_plate_confirmation

OVERRIDES = ["inherit", "on", "off", None]


class TestTruthTable:
    @pytest.mark.parametrize(
        ("override", "require", "clears", "expected"),
        [
            # Only a flagged job on an inheriting printer with the setting on is lifted.
            ("inherit", True, True, False),
            (None, True, True, False),
            # The setting off: nothing to ask for either way.
            ("inherit", False, True, False),
            (None, False, True, False),
            ("inherit", False, False, False),
            (None, False, False, False),
            # No flag: follows the setting, as before.
            ("inherit", True, False, True),
            (None, True, False, True),
            # "Always require" wins over the flag.
            ("on", True, True, True),
            ("on", False, True, True),
            ("on", True, False, True),
            ("on", False, False, True),
            # "Never require" waits for nothing.
            ("off", True, True, False),
            ("off", False, True, False),
            ("off", True, False, False),
            ("off", False, False, False),
        ],
    )
    def test_table(self, override, require, clears, expected):
        assert finish_needs_plate_confirmation(override, require, job_clears_plate=clears) is expected

    def test_default_keeps_the_old_behaviour(self):
        for override, require in itertools.product(OVERRIDES, [True, False]):
            assert finish_needs_plate_confirmation(override, require) == finish_needs_plate_confirmation(
                override, require, job_clears_plate=False
            )

    def test_the_flag_is_keyword_only(self):
        with pytest.raises(TypeError):
            finish_needs_plate_confirmation("inherit", True, True)  # type: ignore[misc]

    @pytest.mark.parametrize("override", OVERRIDES)
    @pytest.mark.parametrize("require", [True, False])
    def test_the_flag_never_adds_a_wait(self, override, require):
        """A flagged job waits at most as often as an unflagged one."""
        flagged = finish_needs_plate_confirmation(override, require, job_clears_plate=True)
        plain = finish_needs_plate_confirmation(override, require)
        assert not (flagged and not plain)

    def test_returns_a_real_bool(self):
        assert finish_needs_plate_confirmation("inherit", True) is True
        assert finish_needs_plate_confirmation("inherit", False, job_clears_plate=True) is False


class TestPlateGateUnaffected:
    """The scheduler's gate reads the printer's state, not the job's flag."""

    @pytest.mark.parametrize("override", OVERRIDES)
    @pytest.mark.parametrize("require", [True, False])
    def test_gate_equals_the_helper_without_the_flag(self, override, require):
        scheduler = PrintScheduler()
        if override is not None:
            scheduler._plate_clear_overrides = {1: override}
        assert scheduler._plate_gate(1, require) is finish_needs_plate_confirmation(override, require)

    def test_gate_has_no_job_parameter(self):
        scheduler = PrintScheduler()
        with pytest.raises(TypeError):
            scheduler._plate_gate(1, True, job_clears_plate=True)  # type: ignore[call-arg]
