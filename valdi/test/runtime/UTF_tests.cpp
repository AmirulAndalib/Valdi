#include "valdi_core/cpp/Text/UTF16Utils.hpp"
#include <gtest/gtest.h>
#include <string>
#include <vector>

using namespace Valdi;

namespace ValdiTest {

TEST(UTF16ToUTF32Index, canResolveIndexesOnEqualLength) {
    std::string_view str = "Hello World\n";

    std::vector<uint32_t> utf32;
    std::vector<char16_t> utf16;

    for (auto c : str) {
        utf32.emplace_back(static_cast<uint32_t>(c));
        utf16.emplace_back(static_cast<char16_t>(c));
    }

    UTF16ToUTF32Index index(utf16.data(), utf16.size(), utf32.data(), utf32.size());

    ASSERT_EQ(static_cast<size_t>(0), index.getUTF32Index(0));
    ASSERT_EQ(static_cast<size_t>(5), index.getUTF32Index(5));
    ASSERT_EQ(static_cast<size_t>(11), index.getUTF32Index(11));
    // Out of bounds should still work
    ASSERT_EQ(static_cast<size_t>(42), index.getUTF32Index(42));
}

TEST(UTF16ToUTF32Index, canResolveIndexesOnDifferentLength) {
    std::string_view str = "مقدمة إلى \U0001F385\U0001F385\u2066C++ \U0001F385 ASCII \U0001F385\U0001F385 MORE ASCII "
                           "\U0001F385 \U0001F385 HERE";

    auto utf16 = utf8ToUtf16(str.data(), str.size());
    auto utf32 = utf8ToUtf32(str.data(), str.size());

    ASSERT_EQ(static_cast<size_t>(54), utf16.second);
    ASSERT_EQ(static_cast<size_t>(47), utf32.second);

    UTF16ToUTF32Index index(utf16.first, utf16.second, utf32.first, utf32.second);

    ASSERT_EQ(static_cast<size_t>(0), index.getUTF32Index(0));
    ASSERT_EQ(static_cast<size_t>(4), index.getUTF32Index(4));
    ASSERT_EQ(static_cast<size_t>(4), index.getUTF32Index(4));
    ASSERT_EQ(static_cast<size_t>(9), index.getUTF32Index(9));
    ASSERT_EQ(static_cast<size_t>(10), index.getUTF32Index(10));
    ASSERT_EQ(static_cast<size_t>(10), index.getUTF32Index(11));
    ASSERT_EQ(static_cast<size_t>(11), index.getUTF32Index(12));
    ASSERT_EQ(static_cast<size_t>(11), index.getUTF32Index(13));
    ASSERT_EQ(static_cast<size_t>(12), index.getUTF32Index(14));
    ASSERT_EQ(static_cast<size_t>(13), index.getUTF32Index(15));
    ASSERT_EQ(static_cast<size_t>(17), index.getUTF32Index(19));
    ASSERT_EQ(static_cast<size_t>(17), index.getUTF32Index(20));
    ASSERT_EQ(static_cast<size_t>(25), index.getUTF32Index(28));
    ASSERT_EQ(static_cast<size_t>(25), index.getUTF32Index(29));
}

// Regression tests for VULN-42385: the decode helpers must never look past `len`.
// Each input lives in a buffer of exactly `len` code units with no NUL terminator,
// mirroring the non-terminated Hermes/JSC StringView storage that reaches these
// converters. A truncated tail must decode to U+FFFD, not an out-of-bounds read.

TEST(UTFConversion, utf16LoneTrailingHighSurrogateEmitsReplacementCharacter) {
    // Final unit is a lone high surrogate. Decoding must not read str[len].
    std::vector<char16_t> input = {u'A', u'B', 0xD800};

    auto utf8 = utf16ToUtf8(input.data(), input.size());

    // "AB" followed by the UTF-8 encoding of U+FFFD (0xEF 0xBF 0xBD).
    ASSERT_EQ(std::string("AB\xEF\xBF\xBD"), std::string(utf8.first, utf8.second));
}

TEST(UTFConversion, utf16DecodeStopsAtLengthAndDoesNotLeakAdjacentUnit) {
    // The unit immediately after the lone high surrogate is itself a low surrogate.
    // Before the fix, the decoder read past `len` and folded that neighbouring unit
    // into a surrogate pair (adjacent-memory info leak). Passing len=3 must stop the
    // decode at the high surrogate and never observe index 3.
    std::vector<char16_t> input = {u'H', u'i', 0xD800, 0xDEAD};

    auto utf8 = utf16ToUtf8(input.data(), 3);

    // Must be "Hi" + U+FFFD, NOT "Hi" + U+102AD (which is what leaking 0xDEAD produced).
    ASSERT_EQ(std::string("Hi\xEF\xBF\xBD"), std::string(utf8.first, utf8.second));
}

TEST(UTFConversion, utf16ValidSurrogatePairAtEndOfBufferIsUnchanged) {
    // Behavior-preserving check: a valid surrogate pair whose low surrogate is the
    // last unit must still decode to the full code point (U+1F385).
    std::vector<char16_t> input = {u'a', 0xD83C, 0xDF85};

    auto utf8 = utf16ToUtf8(input.data(), input.size());

    // 'a' + UTF-8 of U+1F385 (0xF0 0x9F 0x8E 0x85).
    ASSERT_EQ(std::string("a\xF0\x9F\x8E\x85"), std::string(utf8.first, utf8.second));
}

TEST(UTFConversion, utf8TruncatedThreeByteLeadEmitsReplacementCharacter) {
    // Final byte is a truncated 3-byte lead (0xE0). Decoding must not read str[len].
    std::vector<char> input = {'x', 'y', static_cast<char>(0xE0)};

    auto utf16 = utf8ToUtf16(input.data(), input.size());

    std::vector<char16_t> expected = {u'x', u'y', 0xFFFD};
    ASSERT_EQ(expected, std::vector<char16_t>(utf16.first, utf16.first + utf16.second));
}

TEST(UTFConversion, utf8TruncatedFourByteLeadEmitsReplacementCharacters) {
    // 4-byte lead (0xF0) with a single continuation byte, then end of buffer.
    std::vector<char> input = {static_cast<char>(0xF0), static_cast<char>(0x90)};

    auto utf16 = utf8ToUtf16(input.data(), input.size());

    // The truncated lead and the orphaned continuation byte each yield U+FFFD.
    std::vector<char16_t> expected = {0xFFFD, 0xFFFD};
    ASSERT_EQ(expected, std::vector<char16_t>(utf16.first, utf16.first + utf16.second));
}

TEST(UTFConversion, utf8ValidThreeByteSequenceAtEndOfBufferIsUnchanged) {
    // Behavior-preserving check: a complete 3-byte sequence at the tail still decodes.
    // 0xE2 0x82 0xAC is U+20AC (euro sign).
    std::vector<char> input = {'$', static_cast<char>(0xE2), static_cast<char>(0x82), static_cast<char>(0xAC)};

    auto utf16 = utf8ToUtf16(input.data(), input.size());

    std::vector<char16_t> expected = {u'$', 0x20AC};
    ASSERT_EQ(expected, std::vector<char16_t>(utf16.first, utf16.first + utf16.second));
}

} // namespace ValdiTest
