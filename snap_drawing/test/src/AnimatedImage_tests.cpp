#include <cstring>
#include <gtest/gtest.h>
#include <string>

#include "snap_drawing/cpp/Text/IFontManager.hpp"
#include "snap_drawing/cpp/Utils/AnimatedImage.hpp"

namespace snap::drawing {

static Valdi::BytesView bytesFromString(const char* value) {
    return Valdi::BytesView(nullptr, reinterpret_cast<const Valdi::Byte*>(value), strlen(value));
}

TEST(AnimatedImage, undecodablePayloadErrorReportsLengthAndMagicBytes) {
    auto payload = bytesFromString("definitely not an image payload");

    auto image = AnimatedImage::make(nullptr, payload.data(), payload.size());

    ASSERT_FALSE(image);
    const auto message = image.error().toString();
    EXPECT_NE(std::string::npos, message.find("bytes=" + std::to_string(payload.size()))) << message;
    EXPECT_NE(std::string::npos, message.find("magic=64656669")) << message;
}

TEST(AnimatedImage, undecodablePayloadErrorCapsMagicBytes) {
    auto payload = bytesFromString("definitely not an image payload");

    auto image = AnimatedImage::make(nullptr, payload.data(), payload.size());

    ASSERT_FALSE(image);
    const auto message = image.error().toString();
    const auto magicStart = message.find("magic=");
    ASSERT_NE(std::string::npos, magicStart) << message;
    const auto magic = message.substr(magicStart + strlen("magic="));
    EXPECT_EQ(24u, magic.find_first_not_of("0123456789abcdef")) << message;
}

TEST(AnimatedImage, truncatedImageErrorReportsLengthAndMagicBytes) {
    const Valdi::Byte truncatedPng[] = {0x89, 0x50, 0x4E, 0x47};

    auto image = AnimatedImage::make(nullptr, truncatedPng, sizeof(truncatedPng));

    ASSERT_FALSE(image);
    const auto message = image.error().toString();
    EXPECT_NE(std::string::npos, message.find("bytes=4")) << message;
    EXPECT_NE(std::string::npos, message.find("magic=89504e47")) << message;
}

} // namespace snap::drawing
