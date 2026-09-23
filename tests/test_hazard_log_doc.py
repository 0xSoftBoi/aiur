import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "render_hazard_log", ROOT / "tools" / "render_hazard_log.py"
)
assert SPEC is not None and SPEC.loader is not None
render_hazard_log = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render_hazard_log)


class HazardLogDocumentTests(unittest.TestCase):
    def test_document_block_matches_the_registry(self) -> None:
        text = (ROOT / "docs" / "hazard-log.md").read_text(encoding="utf-8")
        self.assertEqual(
            render_hazard_log.splice(text, render_hazard_log.render_block()),
            text,
            "docs/hazard-log.md is stale; run tools/render_hazard_log.py --write",
        )

    def test_block_lists_every_hazard(self) -> None:
        block = render_hazard_log.render_block()
        from aiur.hazards import HAZARDS

        for hazard in HAZARDS:
            self.assertIn(f"`{hazard.id}`", block)

    def test_missing_markers_are_an_error(self) -> None:
        with self.assertRaises(ValueError):
            render_hazard_log.splice("no markers here", render_hazard_log.render_block())


if __name__ == "__main__":
    unittest.main()
