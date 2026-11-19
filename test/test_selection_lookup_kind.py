"""Run with python3 test/test_selection_lookup_kind.py (requires a host C++ compiler).

Which buttons a selection gets: one word -> Translate + Define, a short phrase
inside one paragraph (a name, "pomme de terre") -> Define + Save quote, anything
longer or across paragraphs -> Save quote only.
"""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "src/activities/reader/ClipSelectionActivity.cpp").read_text()
header = (ROOT / "src/activities/reader/ClipSelectionActivity.h").read_text()
word_box = "struct WordBox {" + header.split("struct WordBox {", 1)[1].split("  };", 1)[0] + "};"
kind_decl = "enum class SelectionKind" + header.split("enum class SelectionKind", 1)[1].split(
    "SelectionKind selectionKind() const;", 1
)[0]
signature = "ClipSelectionActivity::SelectionKind ClipSelectionActivity::selectionKind() const"
kind_method = signature + source.split(signature, 1)[1].split("ClippingResult::Action ClipSelectionActivity::", 1)[0]

harness = r"""
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <memory>
struct TextBlock {};
struct EpdFontFamily { enum Style { REGULAR }; };
struct ClipSelectionActivity {
""" + word_box + "\n" + kind_decl + r"""
  SelectionKind selectionKind() const;
  std::unique_ptr<WordBox[]> words = std::make_unique<WordBox[]>(16);
  int selected = 0, rangeStart = -1;
};
""" + kind_method + r"""
using Kind = ClipSelectionActivity::SelectionKind;
// Words of one line, one space apart in the source: "w0 w1 w2 ...".
void line(ClipSelectionActivity& a, int count) {
  uint32_t offset = 0;
  for (int i = 0; i < count; ++i) {
    a.words[i] = {};
    a.words[i].text = "word";
    a.words[i].startOffset = offset;
    a.words[i].endOffset = offset + 4;
    a.words[i].x = static_cast<int16_t>(i * 60);
    a.words[i].width = 50;
    offset += 5;
  }
}
Kind pick(ClipSelectionActivity& a, int from, int to) {
  a.rangeStart = from;
  a.selected = to;
  return a.selectionKind();
}
int main() {
  ClipSelectionActivity a;
  line(a, 10);
  assert(pick(a, 3, 3) == Kind::Word);
  assert(pick(a, 0, 1) == Kind::Phrase);  // "Albert Einstein"
  assert(pick(a, 1, 0) == Kind::Phrase);  // dragged backwards
  assert(pick(a, 0, ClipSelectionActivity::MAX_LOOKUP_PHRASE_WORDS - 1) == Kind::Phrase);
  assert(pick(a, 0, ClipSelectionActivity::MAX_LOOKUP_PHRASE_WORDS) == Kind::Passage);

  // A paragraph break inside the selection makes it a quote; starting on one does not.
  a.words[2].paragraphStart = true;
  assert(pick(a, 1, 2) == Kind::Passage);
  assert(pick(a, 2, 3) == Kind::Phrase);
  a.words[2].paragraphStart = false;

  // A word hyphenated across two lines is still one word.
  a.words[1].startOffset = a.words[0].endOffset;
  a.words[0].discretionaryHyphen = true;
  assert(pick(a, 0, 1) == Kind::Word);
  a.words[0].discretionaryHyphen = false;

  // Without source offsets the layout decides.
  line(a, 10);
  for (int i = 0; i < 10; ++i) a.words[i].startOffset = a.words[i].endOffset = UINT32_MAX;
  assert(pick(a, 0, 1) == Kind::Phrase);
  a.words[2].paragraphStart = true;
  assert(pick(a, 1, 2) == Kind::Passage);
  a.words[2].paragraphStart = false;
  a.words[1].row = 1;
  a.words[1].x = 0;
  a.words[0].discretionaryHyphen = true;
  assert(pick(a, 0, 1) == Kind::Word);

  // Before the range exists the activity behaves as for one word.
  a.rangeStart = -1;
  assert(a.selectionKind() == Kind::Word);
}
"""
with tempfile.TemporaryDirectory() as directory:
    cpp = Path(directory) / "kind.cpp"
    executable = Path(directory) / "kind"
    cpp.write_text(harness)
    subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", str(cpp), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
print("Selection lookup kind checks passed")
