from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import friendly_ui_copy_runtime_module as module


def test_known_verbose_caption_is_shortened(monkeypatch):
    rendered = []

    def original_caption(body, *args, **kwargs):
        rendered.append(body)

    monkeypatch.setattr(module.st, "caption", original_caption)
    monkeypatch.delattr(module.st, "_lte_compact_copy_installed", raising=False)

    module.install_compact_copy_runtime()
    module.st.caption(
        "Die Auswahl wirkt ausschließlich auf die UKL-Exporte. "
        "RailCube-Rohdaten bleiben unverändert. Zusatztext."
    )

    assert rendered == ["Nur für UKL-Exporte. RailCube bleibt unverändert."]


def test_unknown_caption_is_kept(monkeypatch):
    rendered = []

    def original_caption(body, *args, **kwargs):
        rendered.append(body)

    monkeypatch.setattr(module.st, "caption", original_caption)
    monkeypatch.delattr(module.st, "_lte_compact_copy_installed", raising=False)

    module.install_compact_copy_runtime()
    module.st.caption("Unveränderter Hinweis")

    assert rendered == ["Unveränderter Hinweis"]


def test_install_is_idempotent(monkeypatch):
    rendered = []

    def original_caption(body, *args, **kwargs):
        rendered.append(body)

    monkeypatch.setattr(module.st, "caption", original_caption)
    monkeypatch.delattr(module.st, "_lte_compact_copy_installed", raising=False)

    module.install_compact_copy_runtime()
    first_wrapper = module.st.caption
    module.install_compact_copy_runtime()

    assert module.st.caption is first_wrapper
