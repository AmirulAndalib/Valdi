#include "snap_drawing/cpp/Utils/AnimatedImage.hpp"
#include "include/codec/SkCodec.h"
#include "snap_drawing/cpp/Drawing/DrawingContext.hpp"
#include "snap_drawing/cpp/Drawing/Surface/DrawableSurfaceCanvas.hpp"
#include "snap_drawing/cpp/Utils/BytesUtils.hpp"
#include "snap_drawing/cpp/Utils/Image.hpp"
#include "snap_drawing/cpp/Utils/LottieAnimatedImage.hpp"
#include "snap_drawing/cpp/Utils/SVGAnimatedImage.hpp"
#include "snap_drawing/cpp/Utils/SkCodecAnimatedImage.hpp"
#include "valdi_core/cpp/Utils/JSONReader.hpp"

#include <algorithm>
#include <cstdint>
#include <string>
#include <string_view>

namespace snap::drawing {

AnimatedImage::AnimatedImage() = default;
AnimatedImage::~AnimatedImage() = default;

void AnimatedImage::draw(SkCanvas* canvas,
                         const Rect& drawBounds,
                         const Duration& time,
                         FittingSizeMode fittingSizeMode) {
    doDraw(canvas, drawBounds, time, fittingSizeMode);
}

void AnimatedImage::drawInCanvas(const DrawableSurfaceCanvas& canvas,
                                 const Rect& drawBounds,
                                 const Duration& time,
                                 FittingSizeMode fittingSizeMode) {
    doDraw(canvas.getSkiaCanvas(), drawBounds, time, fittingSizeMode);
}

static std::string describePayload(const Valdi::Byte* data, size_t length) {
    static constexpr char kHexDigits[] = "0123456789abcdef";
    static constexpr size_t kMaxMagicBytes = 12;

    const size_t magicLength = std::min(length, kMaxMagicBytes);
    std::string magic;
    magic.reserve(magicLength * 2);
    for (size_t i = 0; i < magicLength; i++) {
        const auto byte = static_cast<uint8_t>(data[i]);
        magic.push_back(kHexDigits[byte >> 4]);
        magic.push_back(kHexDigits[byte & 0x0F]);
    }

    return "bytes=" + std::to_string(length) + " magic=" + magic;
}

Valdi::Result<Ref<AnimatedImage>> AnimatedImage::make(const Ref<IFontManager>& fontManager,
                                                      const Valdi::Byte* data,
                                                      size_t length) {
    Image::initializeCodecs();

    if constexpr (kLottieEnabled) {
        if (isJsonObject(data, length)) {
            return LottieAnimatedImage::make(fontManager, data, length).map<Ref<AnimatedImage>>();
        }
    }

    const Valdi::BytesView bytesView(nullptr, data, length);
    if (Image::isSVG(bytesView)) {
        return SVGAnimatedImage::make(data, length).map<Ref<AnimatedImage>>();
    }

    auto skData = skDataFromBytes(bytesView, DataConversionModeAlwaysCopy);
    auto codec = SkCodec::MakeFromData(skData);
    if (codec == nullptr) {
        const auto message = "Unsupported image format (" + describePayload(data, length) + ")";
        return Valdi::Error(std::string_view(message));
    }
    return SkCodecAnimatedImage::make(std::move(codec)).map<Ref<AnimatedImage>>();
}

bool AnimatedImage::isJsonObject(const Valdi::Byte* data, size_t length) {
    // Fuzzy but efficient check for JSON, and if so assume Lottie
    Valdi::JSONReader reader(std::string_view(reinterpret_cast<const char*>(data), length));
    return reader.parseBeginObject();
}

} // namespace snap::drawing
