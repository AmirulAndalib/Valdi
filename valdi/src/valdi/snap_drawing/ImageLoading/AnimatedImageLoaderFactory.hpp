//
//  AnimatedImageLoaderFactory.hpp
//  valdi-desktop-apple
//
//  Created by Simon Corsin on 7/22/22.
//

#pragma once

#include "snap_drawing/cpp/Utils/Aliases.hpp"

#include "valdi/runtime/Interfaces/IRemoteDownloader.hpp"
#include "valdi/runtime/Resources/AssetLoaderFactory.hpp"

#include "snap_drawing/cpp/Utils/AnimatedImage.hpp"

#include <string>

namespace snap::drawing {

class Resources;

/**
 Describes an asset url for a decode-error message using only its host and file extension. A media
 url's path and query can carry media ids and decryption keys, which must not reach an error string
 that ships to the crash reporting pipeline. A `composer-encrypted-*` wrapper url is described by
 its inner `url=` target, so the reported host is the CDN actually serving the bytes rather than the
 wrapper scheme. Declared here so the sanitizing is directly testable.
 */
std::string describeAnimatedImageAssetSource(const Valdi::StringBox& url);

class AnimatedImageLoaderFactory : public Valdi::AssetLoaderFactory {
public:
    explicit AnimatedImageLoaderFactory(const Ref<Resources>& resources);
    ~AnimatedImageLoaderFactory() override;

    snap::valdi_core::AssetOutputType getOutputType() const override;

    Valdi::Ref<Valdi::AssetLoader> createAssetLoader(const std::vector<Valdi::StringBox>& urlSchemes,
                                                     const Ref<Valdi::IRemoteDownloader>& downloader) override;

private:
    Ref<Resources> _resources;
};

} // namespace snap::drawing
