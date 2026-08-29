#include "valdi/snap_drawing/ImageLoading/AnimatedImageLoaderFactory.hpp"

#include <gtest/gtest.h>

#include <string>

using namespace Valdi;
using namespace snap::drawing;

TEST(AnimatedImageAssetSource, reportsHostAndExtension) {
    EXPECT_EQ("host=cf-st.sc-cdn.net ext=webp",
              describeAnimatedImageAssetSource(StringBox::fromCString("https://cf-st.sc-cdn.net/media/sticker.webp")));
}

TEST(AnimatedImageAssetSource, dropsQueryAndFragment) {
    EXPECT_EQ("host=cf-st.sc-cdn.net ext=webp",
              describeAnimatedImageAssetSource(
                  StringBox::fromCString("https://cf-st.sc-cdn.net/media/sticker.webp?key=THEKEY&iv=THEIV#frag")));
    EXPECT_EQ("host=cf-st.sc-cdn.net ext=none",
              describeAnimatedImageAssetSource(StringBox::fromCString("https://cf-st.sc-cdn.net?key=THEKEY")));
    EXPECT_EQ("host=cf-st.sc-cdn.net ext=none",
              describeAnimatedImageAssetSource(StringBox::fromCString("https://cf-st.sc-cdn.net#THEKEY")));
}

TEST(AnimatedImageAssetSource, ignoresADotInADirectoryName) {
    EXPECT_EQ(
        "host=cf-st.sc-cdn.net ext=none",
        describeAnimatedImageAssetSource(StringBox::fromCString("https://cf-st.sc-cdn.net/media/123.456/secret")));
}

TEST(AnimatedImageAssetSource, clampsALongExtension) {
    EXPECT_EQ("host=host ext=aaaaaaaa",
              describeAnimatedImageAssetSource(StringBox::fromCString("https://host/a.aaaaaaaaaaaaaaaa")));
}

TEST(AnimatedImageAssetSource, reportsNoHostForASchemelessSource) {
    EXPECT_EQ("host=none", describeAnimatedImageAssetSource(StringBox::fromCString("{\"v\":\"5.7.4\",\"layers\":[]}")));
}

TEST(AnimatedImageAssetSource, describesAWrapperUrlByItsInnerTarget) {
    const auto described = describeAnimatedImageAssetSource(StringBox::fromCString(
        "composer-encrypted-thumbnail://?url=https%3A%2F%2Fcf-st.sc-cdn.net%2Fthumb.jpg&key=THEKEY&iv=THEIV"));

    EXPECT_EQ("host=cf-st.sc-cdn.net ext=jpg wrapper=composer-encrypted-thumbnail", described);
    EXPECT_EQ(std::string::npos, described.find("THEKEY"));
    EXPECT_EQ(std::string::npos, described.find("THEIV"));
}

TEST(AnimatedImageAssetSource, reportsTheWrapperWhenItCarriesNoInnerTarget) {
    EXPECT_EQ(
        "host=none wrapper=composer-encrypted-image",
        describeAnimatedImageAssetSource(StringBox::fromCString("composer-encrypted-image://?contentObject=AQID")));
    EXPECT_EQ("host=none wrapper=composer-encrypted-image",
              describeAnimatedImageAssetSource(StringBox::fromCString("composer-encrypted-image://profile-icon")));
}

TEST(AnimatedImageAssetSource, ignoresAnInnerTargetThatIsNotAWholeQueryParameter) {
    EXPECT_EQ("host=none wrapper=composer-encrypted-thumbnail",
              describeAnimatedImageAssetSource(
                  StringBox::fromCString("composer-encrypted-thumbnail://?contenturl=https%3A%2F%2Fhost%2Fa.jpg")));
}

TEST(AnimatedImageAssetSource, capsALongHost) {
    const std::string url = "https://" + std::string(2000, 'a') + "/sticker.jpg";

    EXPECT_EQ("host=" + std::string(64, 'a') + " ext=jpg",
              describeAnimatedImageAssetSource(StringBox::fromString(url)));
}

TEST(AnimatedImageAssetSource, capsALongWrappedUrlBeforeDecodingIt) {
    const std::string url =
        "composer-encrypted-thumbnail://?url=https%3A%2F%2F" + std::string(2000, 'b') + "%2Fthumb.jpg&key=THEKEY";

    const auto described = describeAnimatedImageAssetSource(StringBox::fromString(url));

    EXPECT_EQ("host=" + std::string(64, 'b') + " ext=none wrapper=composer-encrypted-thumbnail", described);
    EXPECT_EQ(std::string::npos, described.find("THEKEY"));
}
