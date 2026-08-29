//
//  AnimatedImageLoaderFactory.cpp
//  valdi-desktop-apple
//
//  Created by Simon Corsin on 7/22/22.
//

#include "valdi/snap_drawing/ImageLoading/AnimatedImageLoaderFactory.hpp"
#include "snap_drawing/cpp/Resources.hpp"
#include "snap_drawing/cpp/Text/IFontManager.hpp"
#include "valdi/runtime/Resources/AssetLoader.hpp"
#include "valdi/runtime/Resources/AssetLoaderCompletion.hpp"

#include <string>
#include <string_view>

namespace snap::drawing {

namespace {

constexpr size_t kMaxExtensionLength = 8;
constexpr size_t kMaxHostLength = 64;
constexpr size_t kMaxEncodedUrlLength = 1024;
constexpr std::string_view kWrapperSchemePrefix = "composer-encrypted";

int hexDigitValue(char digit) {
    if (digit >= '0' && digit <= '9') {
        return digit - '0';
    }
    if (digit >= 'a' && digit <= 'f') {
        return digit - 'a' + 10;
    }
    if (digit >= 'A' && digit <= 'F') {
        return digit - 'A' + 10;
    }
    return -1;
}

std::string percentDecoded(std::string_view value) {
    if (value.size() > kMaxEncodedUrlLength) {
        value = value.substr(0, kMaxEncodedUrlLength);
    }

    std::string decoded;
    decoded.reserve(value.size());

    for (size_t i = 0; i < value.size(); i++) {
        if (value[i] == '%' && i + 2 < value.size()) {
            const auto high = hexDigitValue(value[i + 1]);
            const auto low = hexDigitValue(value[i + 2]);
            if (high >= 0 && low >= 0) {
                decoded.push_back(static_cast<char>(high * 16 + low));
                i += 2;
                continue;
            }
        }
        decoded.push_back(value[i]);
    }

    return decoded;
}

std::string_view wrappedUrlParameter(std::string_view raw) {
    for (auto start = raw.find("url="); start != std::string_view::npos; start = raw.find("url=", start + 1)) {
        if (start == 0 || raw[start - 1] == '?' || raw[start - 1] == '&') {
            const auto value = raw.substr(start + 4);
            const auto valueEnd = value.find_first_of("&#");
            return valueEnd == std::string_view::npos ? value : value.substr(0, valueEnd);
        }
    }

    return {};
}

std::string describeHostAndExtension(std::string_view raw) {
    const auto schemeEnd = raw.find("://");
    if (schemeEnd == std::string_view::npos) {
        return "host=none";
    }

    const auto authority = raw.substr(schemeEnd + 3);
    const auto hostEnd = authority.find_first_of("/?#");
    const auto host = hostEnd == std::string_view::npos ? authority : authority.substr(0, hostEnd);

    auto path = hostEnd == std::string_view::npos ? std::string_view() : authority.substr(hostEnd);
    const auto pathEnd = path.find_first_of("?#");
    if (pathEnd != std::string_view::npos) {
        path = path.substr(0, pathEnd);
    }

    const auto lastSlash = path.rfind('/');
    const auto extensionStart = path.rfind('.');
    const auto hasExtension =
        extensionStart != std::string_view::npos && (lastSlash == std::string_view::npos || extensionStart > lastSlash);
    const auto extension =
        hasExtension ? path.substr(extensionStart + 1, kMaxExtensionLength) : std::string_view("none");

    return "host=" + std::string(host.substr(0, kMaxHostLength)) + " ext=" + std::string(extension);
}

} // namespace

std::string describeAnimatedImageAssetSource(const Valdi::StringBox& url) {
    const auto raw = url.toStringView();
    const auto schemeEnd = raw.find("://");
    if (schemeEnd == std::string_view::npos) {
        return "host=none";
    }

    const auto scheme = raw.substr(0, schemeEnd);
    if (scheme.rfind(kWrapperSchemePrefix, 0) != 0) {
        return describeHostAndExtension(raw);
    }

    const auto wrapper = " wrapper=" + std::string(scheme);
    const auto inner = wrappedUrlParameter(raw.substr(schemeEnd + 3));
    if (inner.empty()) {
        return "host=none" + wrapper;
    }

    return describeHostAndExtension(percentDecoded(inner)) + wrapper;
}

class AnimatedImageLoader : public Valdi::AssetLoader {
public:
    AnimatedImageLoader(const Ref<Resources>& resources,
                        std::vector<Valdi::StringBox>&& supportedSchemes,
                        const Valdi::Ref<Valdi::IRemoteDownloader>& downloader)
        : Valdi::AssetLoader(std::move(supportedSchemes)), _resources(resources), _downloader(downloader) {}
    ~AnimatedImageLoader() override = default;

    snap::valdi_core::AssetOutputType getOutputType() const override {
        return snap::valdi_core::AssetOutputType::Lottie;
    }

    Valdi::Result<Valdi::Value> requestPayloadFromURL(const Valdi::StringBox& url) override {
        return Valdi::Value(url);
    }

    Valdi::Shared<snap::valdi_core::Cancelable> loadAsset(
        const Valdi::Value& requestPayload,
        int32_t preferredWidth,
        int32_t preferredHeight,
        const Valdi::Value& associatedData,
        const Valdi::Ref<Valdi::AssetLoaderCompletion>& completion) override {
        auto fontManager = associatedData.getTypedRef<IFontManager>();

        auto url = requestPayload.toStringBox();

        return _downloader->downloadItem(
            url, [weakSelf = Valdi::weakRef(this), fontManager, completion, url](const auto& result) {
                if (auto strongSelf = weakSelf.lock()) {
                    strongSelf->onBytesLoaded(result, fontManager, completion, url);
                }
            });
    }

private:
    Ref<Resources> _resources;
    Valdi::Ref<Valdi::IRemoteDownloader> _downloader;

    void onBytesLoaded(const Valdi::Result<Valdi::BytesView>& result,
                       const Valdi::Ref<IFontManager>& fontManager,
                       const Valdi::Ref<Valdi::AssetLoaderCompletion>& completion,
                       const Valdi::StringBox& url) {
        if (!result) {
            completion->onLoadComplete(result.error());
            return;
        }

        auto scene = AnimatedImage::make(fontManager != nullptr ? fontManager : _resources->getFontManager(),
                                         result.value().data(),
                                         result.value().size());
        if (!scene) {
            const auto message = std::string(scene.error().getMessage().toStringView()) + " [" +
                                 describeAnimatedImageAssetSource(url) + "]";
            completion->onLoadComplete(Valdi::Error(std::string_view(message)));
            return;
        }

        Valdi::Ref<Valdi::LoadedAsset> loadedAsset = scene.moveValue();
        completion->onLoadComplete(loadedAsset);
    }
};

AnimatedImageLoaderFactory::AnimatedImageLoaderFactory(const Ref<Resources>& resources) : _resources(resources) {}
AnimatedImageLoaderFactory::~AnimatedImageLoaderFactory() = default;

snap::valdi_core::AssetOutputType AnimatedImageLoaderFactory::getOutputType() const {
    return snap::valdi_core::AssetOutputType::Lottie;
}

Valdi::Ref<Valdi::AssetLoader> AnimatedImageLoaderFactory::createAssetLoader(
    const std::vector<Valdi::StringBox>& urlSchemes, const Ref<Valdi::IRemoteDownloader>& downloader) {
    return Valdi::makeShared<AnimatedImageLoader>(_resources, std::vector<Valdi::StringBox>(urlSchemes), downloader);
}

} // namespace snap::drawing
