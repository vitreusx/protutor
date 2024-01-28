from concurrent.futures import ThreadPoolExecutor
import subprocess as sp
import argparse
from pathlib import Path
from TexSoup import TexSoup, TexNode
from TexSoup.tex import TexText
import re
import pickle
import asyncio
import logging


def unit(value):
    fut = asyncio.Future()
    fut.set_result(value)
    return fut


def remove_accents(ipa: str):
    return re.sub("[ˈˌ]", "", ipa)


class Engine:
    def __init__(self, lang: str, cache_dir="~/.cache/protutor"):
        self._lang = lang

        self._cache_path = Path(cache_dir).expanduser() / f"words_{lang}.pkl"
        if self._cache_path.exists():
            with open(self._cache_path, "rb") as f:
                self._cache = pickle.load(f)
        else:
            self._cache = {}

    async def to_IPA(self, text: str, lang=None):
        """Get IPA pronunciation for a word or an entire phrase."""

        text = text.lower()
        text = re.sub(r"[^\w\s]", "", text)

        if lang is None:
            lang = self._lang

        if " " in text or text not in self._cache:
            cmd = ["/usr/bin/espeak-ng", "-q", f"-v{lang}", "--ipa", text]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
            )
            ipa, _ = await proc.communicate()
            ipa = ipa.decode("utf-8").strip()

            if " " not in text:
                self._cache[text] = ipa
                self._cache_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._cache_path, "wb") as f:
                    pickle.dump(self._cache, f)

        else:
            ipa = self._cache[text]

        return ipa

    async def annotate_clause(self, clause: str):
        """Annotate a clause (= words separated by space).
        :param clause: Clause to annotate.
        :return: List of pairs (text, ipa) with chunks of `clause` and corresponding IPA prounciation strings.
        """

        words = clause.split()
        clause = " ".join(words)
        text_IPA = await self.to_IPA(clause)
        text_IPA_ = remove_accents(text_IPA)
        suffix_IPA_ = text_IPA_ + " "

        res = []
        i = 0
        while i < len(words):
            word = words[i]
            word_IPA = await self.to_IPA(word)
            word_IPA_ = remove_accents(word_IPA)
            if suffix_IPA_.startswith(word_IPA_ + " "):
                res.append((word, word_IPA))
                suffix_IPA_ = suffix_IPA_[len(word_IPA_) + 1 :].lstrip()
                i += 1
            else:
                j = i + 1
                while j <= len(words):
                    prefix = " ".join(words[:j])
                    prefix_IPA = await self.to_IPA(prefix)
                    prefix_IPA_ = remove_accents(prefix_IPA)
                    if text_IPA_.startswith(prefix_IPA_ + " "):
                        break
                    j += 1

                linked = " ".join(words[i:j])
                linked_IPA = await self.to_IPA(linked)
                res.append((linked, linked_IPA))

                suffix_IPA = text_IPA.removeprefix(prefix_IPA).lstrip()
                suffix_IPA_ = remove_accents(suffix_IPA) + " "
                i = j

        return res

    async def annotate_text(self, text: str):
        """Annotate any text.
        :param text: Text to annotate.
        :return: List of pairs (part, ipa) with parts of `text` and corresponding IPA pronunciations.
        """

        paragraphs = text.split("\n")
        res = []
        for idx, par in enumerate(paragraphs):
            if idx > 0:
                value = [("\n", None)]
                res.append(unit(value))

            clauses = [*re.finditer("[^\w ’]+", par)]
            cur = 0
            for idx, match in enumerate(clauses):
                beg, end = match.span()
                if idx == len(clauses) - 1:
                    end = len(par)
                res.append(self.annotate_clause(par[cur:end]))
                cur = end

        res = await asyncio.gather(*res)
        res = [x for y in res for x in y]
        return res

    def _ann_to_text(self, ann: list[tuple[str, str | None]]) -> str:
        """Transform annotations-as-list to text."""
        res = []
        for text, ipa in ann:
            if ipa is not None:
                text = rf"\ipa{{{text}}}{{{ipa}}}"
            res.append(text)
        return "".join(res)

    async def transform_tex_file(self, tex_code: str):
        """Transform TeX source code, adding to each word/linked clause pronunciation guide above."""

        soup = TexSoup(tex_code)

        with open(Path(__file__).parent / "preamble.tex", "r") as f:
            preamble = TexSoup(f.read())

        for idx, node in enumerate(soup.all):
            if node.name == "document":
                soup.insert(idx, preamble)

        for node in soup.document.all:
            if node.name != "text":
                continue

            text = node.expr.string
            ann = await self.annotate_text(text)
            ann_text = self._ann_to_text(ann)
            node.replace_with(TexNode(TexText(ann_text)))

        return str(soup)
