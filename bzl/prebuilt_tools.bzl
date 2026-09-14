# Shim to use different dependencies for open source and internal valdi

INTERNAL_BUILD = True

def valdi_compiler_companion_files():
    if INTERNAL_BUILD:
        return ["@valdi_compiler_companion//:all_files"]
    return native.glob([
        "compiler_companion/**/*.js",
        "compiler_companion/**/*.js.map",
        "compiler_companion/**/*.node",
    ])

def bundle_js():
    if INTERNAL_BUILD:
        return "@valdi_compiler_companion//:bundle.js"
    return "//compiler_companion:bundle.js"

def jscore_library():
    if INTERNAL_BUILD:
        return "@jscore_libs//:linux/x86_64/libjsc.so"
    return None

def jscore_import(name):
    """Defines the jscore import library.

    The prebuilt libjsc.so only exists for internal linux/x86_64 builds. Bazel 8's
    cc_import fails analysis when handed no library, so the cc_import is defined
    only when a prebuilt is available; `name` is a cc_library that links it solely
    on linux/x86_64 and is empty on every other platform (core //valdi still
    depends on this target there).
    """
    prebuilt = jscore_library()
    if prebuilt:
        native.cc_import(
            name = name + "_prebuilt",
            shared_library = prebuilt,
            visibility = ["//visibility:private"],
        )
        native.cc_library(
            name = name,
            visibility = ["//visibility:public"],
            deps = select({
                "//bzl/conditions:linux_x64": [":" + name + "_prebuilt"],
                "//conditions:default": [],
            }),
        )
    else:
        native.cc_library(
            name = name,
            visibility = ["//visibility:public"],
        )
