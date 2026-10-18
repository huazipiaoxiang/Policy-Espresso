"""政策 2.0 语料库加载（09 §2.2）：seed/cepa/*.md 带 front-matter 元数据。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parents[3] / "seed" / "cepa"

_FRONT_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


@dataclass
class CorpusDoc:
    doc_id: str
    title: str
    issuing_bodies: list[str]
    doc_number: str
    published_at: str  # YYYY-MM-DD
    validity: str  # 有效 / 已修订 / 已废止
    themes: list[str]
    jurisdiction: str
    body: str
    path: str = ""

    @property
    def effective(self) -> bool:
        """有效性判断（人工确认一次的机读表示）：已废止不得作为依据。"""
        return self.validity.startswith("有效") or self.validity.startswith("已修订")


@dataclass
class Corpus:
    docs: list[CorpusDoc] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(f"【{d.title}】\n{d.body}" for d in self.docs)

    @property
    def themes(self) -> list[str]:
        seen: list[str] = []
        for d in self.docs:
            for t in d.themes:
                if t not in seen:
                    seen.append(t)
        return seen


def _parse_meta(block: str) -> dict:
    meta: dict = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            value = [v.strip() for v in value[1:-1].split(",") if v.strip()]
        meta[key.strip()] = value
    return meta


def load_corpus(include_all_validity: bool = False) -> Corpus:
    """加载语料。默认只含现行有效/已修订文件（已废止不得作依据，T2-09）。"""
    docs: list[CorpusDoc] = []
    if not SEED_DIR.exists():
        return Corpus(docs=docs)
    for path in sorted(SEED_DIR.glob("*.md")):
        m = _FRONT_RE.match(path.read_text(encoding="utf-8"))
        if not m:
            continue
        meta = _parse_meta(m.group(1))
        doc = CorpusDoc(
            doc_id=meta.get("doc_id", path.stem),
            title=meta.get("title", path.stem),
            issuing_bodies=meta.get("issuing_bodies", []) or [],
            doc_number=meta.get("doc_number", ""),
            published_at=str(meta.get("published_at", "")),
            validity=meta.get("validity", ""),
            themes=meta.get("themes", []) or [],
            jurisdiction=meta.get("jurisdiction", "GBA"),
            body=m.group(2).strip(),
            path=str(path),
        )
        if include_all_validity or doc.effective:
            docs.append(doc)
    return Corpus(docs=docs)
