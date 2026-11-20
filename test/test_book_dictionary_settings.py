"""Compile BookDictionarySettings against an SdFat-like storage and check saves.

SdFat's mkdir creates the last path component with O_EXCL, so it returns false
when the folder already exists. Choosing a dictionary for a second book (or a
second time for one book) must still save.
"""

from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]

STUBS = {
    "Logging.h": '#pragma once\n#define LOG_ERR(...) ((void)0)\n',
    "HalStorage.h": r'''
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <vector>

namespace fake {
inline std::map<std::string, std::shared_ptr<std::vector<uint8_t>>> files;
inline std::set<std::string> directories{"/", "/.crosspoint"};
}  // namespace fake

class HalFile {
 public:
  std::shared_ptr<std::vector<uint8_t>> bytes;
  size_t pos = 0;
  int read(void* out, size_t size) {
    if (!bytes) return -1;
    size = std::min(size, bytes->size() - std::min(pos, bytes->size()));
    std::memcpy(out, bytes->data() + pos, size);
    pos += size;
    return int(size);
  }
  size_t write(const uint8_t* data, size_t size) {
    if (!bytes) return 0;
    bytes->resize(std::max(bytes->size(), pos + size));
    std::memcpy(bytes->data() + pos, data, size);
    pos += size;
    return size;
  }
  size_t size() const { return bytes ? bytes->size() : 0; }
};

class HalStorage {
 public:
  static HalStorage& getInstance() {
    static HalStorage storage;
    return storage;
  }
  bool exists(const char* path) const { return fake::directories.count(path) || fake::files.count(path); }
  // Same contract as SdFat FatFile::mkdir: the last component is created with
  // O_EXCL, so an existing folder is a failure.
  bool mkdir(const char* path, bool = true) {
    if (exists(path)) return false;
    fake::directories.insert(path);
    return true;
  }
  bool remove(const char* path) { return fake::files.erase(path) != 0; }
  bool openFileForRead(const char*, const char* path, HalFile& file) {
    file = {};
    const auto found = fake::files.find(path);
    if (found == fake::files.end()) return false;
    file.bytes = found->second;
    return true;
  }
  bool openFileForWrite(const char*, const char* path, HalFile& file) {
    std::string parent(path);
    parent.erase(parent.find_last_of('/'));
    file = {};
    if (!fake::directories.count(parent)) return false;
    auto& bytes = fake::files[path];
    bytes = std::make_shared<std::vector<uint8_t>>();
    file.bytes = bytes;
    return true;
  }
};

#define Storage HalStorage::getInstance()
''',
}

CHECK = r'''
#include <BookDictionarySettings.h>
#include <cassert>
#include <cstdio>
#include <cstring>

static bookdictionary::Settings choose(const char* name) {
  bookdictionary::Settings settings;
  settings.overrides = 1;
  std::snprintf(settings.definition, sizeof(settings.definition), "%s", name);
  return settings;
}

int main() {
  const char* french = "/Livres/Le Rouge et le Noir.epub";
  const char* english = "/Books/The Kybalion.epub";
  bookdictionary::Settings loaded;

  // First choice ever: the folder does not exist yet.
  assert(bookdictionary::save(french, choose("fr-en-complet")));
  // A second book, folder already there.
  assert(bookdictionary::save(english, choose("en-complet")));
  assert(bookdictionary::load(english, loaded) && std::strcmp(loaded.definition, "en-complet") == 0);
  // Changing the choice of a book that already has one.
  assert(bookdictionary::save(french, choose("en-complet")));
  assert(bookdictionary::load(french, loaded) && std::strcmp(loaded.definition, "en-complet") == 0);
  assert(bookdictionary::save(french, choose("fr-en-complet")));
  assert(bookdictionary::load(french, loaded) && std::strcmp(loaded.definition, "fr-en-complet") == 0);
}
'''


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="book-dictionary-test-") as directory:
        work = Path(directory)
        for name, content in STUBS.items():
            (work / name).write_text(content)
        (work / "check.cpp").write_text(CHECK)
        subprocess.run([
            "c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
            f"-I{work}", f"-I{ROOT / 'src/util'}",
            str(ROOT / "src/util/BookDictionarySettings.cpp"), str(work / "check.cpp"),
            "-o", str(work / "check"),
        ], check=True)
        subprocess.run([str(work / "check")], check=True)
    print("Book dictionary settings checks passed")
