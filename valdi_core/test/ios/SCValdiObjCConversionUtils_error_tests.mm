
#include <gtest/gtest.h>
#import "valdi_core/SCValdiObjCConversionUtils.h"

#include "valdi_core/cpp/Utils/Error.hpp"
#include "valdi_core/cpp/Utils/StringCache.hpp"

namespace {

Valdi::StringBox makeString(const char* str) {
    return Valdi::StringCache::getGlobal().makeString(std::string_view(str));
}

TEST(SCValdiObjCConversionUtilsError, messageOnlyError) {
    @autoreleasepool {
        NSError* nsError = ValdiIOS::NSErrorFromError(Valdi::Error("boom"));

        EXPECT_STREQ("com.snap.valdi", nsError.domain.UTF8String);
        EXPECT_EQ(0, nsError.code);
        EXPECT_STREQ("boom", nsError.localizedDescription.UTF8String);
        EXPECT_EQ(nil, nsError.userInfo[@"SCValdiErrorStackTrace"]);
    }
}

TEST(SCValdiObjCConversionUtilsError, stackTraceIsPreservedInUserInfo) {
    @autoreleasepool {
        Valdi::Error error(makeString("boom"), makeString("frame1\nframe2"), nullptr);
        NSError* nsError = ValdiIOS::NSErrorFromError(error);

        EXPECT_STREQ("boom", nsError.localizedDescription.UTF8String);
        NSString* stackTrace = nsError.userInfo[@"SCValdiErrorStackTrace"];
        ASSERT_NE(nil, stackTrace);
        EXPECT_STREQ("frame1\nframe2", stackTrace.UTF8String);
    }
}

TEST(SCValdiObjCConversionUtilsError, causeChainIsFlattenedIntoMessage) {
    @autoreleasepool {
        Valdi::Error inner(makeString("inner failure"), makeString("inner stack"), nullptr);
        Valdi::Error outer = inner.rethrow("outer context");

        NSError* nsError = ValdiIOS::NSErrorFromError(outer);

        EXPECT_STREQ("outer context\n[caused by]: inner failure", nsError.localizedDescription.UTF8String);
        NSString* stackTrace = nsError.userInfo[@"SCValdiErrorStackTrace"];
        ASSERT_NE(nil, stackTrace);
        EXPECT_STREQ("inner stack", stackTrace.UTF8String);
    }
}

TEST(SCValdiObjCConversionUtilsError, errorCodeIsPreserved) {
    @autoreleasepool {
        Valdi::Error error(makeString("grpc failure"), 14);
        NSError* nsError = ValdiIOS::NSErrorFromError(error);

        EXPECT_EQ(14, nsError.code);
        EXPECT_STREQ("grpc failure", nsError.localizedDescription.UTF8String);
    }
}

TEST(SCValdiObjCConversionUtilsError, emptyErrorGetsPlaceholderMessage) {
    @autoreleasepool {
        NSError* nsError = ValdiIOS::NSErrorFromError(Valdi::Error());

        EXPECT_STREQ("Empty Error", nsError.localizedDescription.UTF8String);
    }
}

} // namespace
