//
//  SCValdiBridgeFunction.h
//  valdi_core-ios
//
//  Created by Simon Corsin on 1/31/23.
//

#import "valdi_core/SCMacros.h"
#import "valdi_core/SCValdiJSRuntime.h"
#import "valdi_core/SCValdiMarshallableObject.h"
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/**
 * Error domain for NSErrors produced by resolveFunctionWithJSRuntime:error:.
 */
FOUNDATION_EXPORT NSString* const SCValdiBridgeFunctionErrorDomain;

@interface SCValdiBridgeFunction : SCValdiMarshallableObject

@property (readonly, nonatomic) id callBlock;

VALDI_NO_INIT

/**
 Return the module path used by the function.
 Will be overriden by generated classes from the @GenerateNativeFunction
 code annotation.
 */
+ (NSString*)modulePath;

/**
 * Returns whether async strict mode is enabled for this function.
 * Will be overridden by generated classes.
 */
+ (BOOL)asyncStrictMode;

/**
 * Resolve and instantiate the function from the given JSRuntime instance
 */
+ (nonnull instancetype)functionWithJSRuntime:(nonnull id<SCValdiJSRuntime>)jsRuntime;

/**
 * Resolve and instantiate the function from the given JSRuntime instance, without raising.
 *
 * functionWithJSRuntime: raises an SCValdiError (NSException) when resolution fails -- e.g. when
 * the JS runtime has been torn down (logout) while the caller is still active. Swift cannot catch
 * NSException, so a failure below a Swift frame terminates the process. Swift callers must use
 * this variant instead: resolution failures are reported as an NSError and a nil return.
 *
 * Programming errors (a failed NSAssert, an unrecognized selector) still raise, deliberately.
 */
+ (nullable instancetype)resolveFunctionWithJSRuntime:(nonnull id<SCValdiJSRuntime>)jsRuntime
                                                error:(NSError* _Nullable* _Nullable)error
    NS_SWIFT_NAME(resolve(jsRuntime:));

@end

extern id SCValdiMakeBridgeFunctionFromJSRuntime(Class objectClass, id<SCValdiJSRuntime> jsRuntime, NSString* path);

NS_ASSUME_NONNULL_END
