//
//  SCValdiBridgeFunction.m
//  valdi_core-ios
//
//  Created by Simon Corsin on 1/31/23.
//

#import "valdi_core/SCValdiBridgeFunction.h"
#import "valdi_core/SCValdiMarshallableObjectRegistry.h"
#import "valdi_core/SCValdiMarshallableObjectUtils.h"
#import "valdi_core/SCValdiError.h"
#import "valdi_core/SCValdiMarshaller.h"

NSString *const SCValdiBridgeFunctionErrorDomain = @"SCValdiBridgeFunctionErrorDomain";

static id SCValdiMakeDegradedBridgeFunction(Class objectClass)
{
    // The JS runtime was torn down mid-resolution. Return a function whose callBlock is a no-op so a
    // dying session unwinds quietly instead of aborting. Returning nil is not an option: the raising
    // resolver is imported into Swift as non-null, so nil would trap on first use. The no-op block is
    // intentionally nullary; generated forwarders cast callBlock to a typed block and invoke it, and
    // on arm64 a call through a wider block signature safely ignores the extra arguments and yields
    // nil/0 for the object/void/integral return types these functions produce.
    static id kNoopCallBlock;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        kNoopCallBlock = ^id{ return nil; };
    });
    SCValdiMarshallableObjectRegistry *objectRegistry = SCValdiMarshallableObjectRegistryGetSharedInstance();
    return [objectRegistry makeObjectWithFieldValuesOfClass:objectClass, kNoopCallBlock];
}

@implementation SCValdiBridgeFunction

- (id)callBlock
{
    return SCValdiFieldValueGetObject(SCValdiGetMarshallableObjectFieldsStorage(self)[0]);
}

+ (NSString *)modulePath
{
    NSString *className = NSStringFromClass([self class]);
    SCValdiErrorThrow([NSString stringWithFormat:@"Function class %@ should override the 'modulePath' class method", className]);
}

+ (BOOL)asyncStrictMode
{
    return NO;
}

+ (instancetype)functionWithJSRuntime:(id<SCValdiJSRuntime>)jsRuntime
{
    if ([self asyncStrictMode]) {
        NSAssert(![NSThread isMainThread],
                 @"When async_strict_mode is enabled, function resolution (functionWithJSRuntime:) must not be called from the main thread (to avoid ANRs). Use a background thread, the JS thread, or invokeWithJSRuntimeProvider:completionHandler:.");
    }
    // This raising resolver is imported into Swift as non-null and used by the majority of call sites,
    // so a raised SCValdiError below a Swift frame aborts the app. When resolution is skipped because
    // the JS runtime was torn down (e.g. logout), degrade to a no-op function instead of raising.
    // Genuine resolution failures on a live runtime still raise. The non-raising
    // resolveFunctionWithJSRuntime:error: keeps reporting nil+error so its adopters run their own
    // degrade path.
    SCValdiMarshallerScoped(marshaller, {
        SCValdiMarshallableObjectRegistry *objectRegistry = SCValdiMarshallableObjectRegistryGetSharedInstance();
        [objectRegistry setSchemaOfClass:self inMarshaller:marshaller];
        NSInteger objectIndex = [jsRuntime pushModuleAtPath:[self modulePath] reportingErrorOnMarshaller:marshaller];
        // Kill switch lives here, indirectly. This degrade fires only when the marshaller carries the
        // teardown error code (kResolutionSkippedDuringTeardownErrorCode). That code is stamped ONLY
        // when the VALDI_ENABLE_RESOLUTION_TEARDOWN_DEGRADE tweak is on (see
        // JavaScriptRuntime::pushModuleToMarshaller; default on). With the flag off, C++ omits the
        // code, ConsumeResolutionTeardownError returns NO, and this path raises exactly as before. The
        // flag is read in C++ because the runtime tweaks aren't exposed to this ObjC layer.
        if (SCValdiMarshallerConsumeResolutionTeardownError(marshaller)) {
            return SCValdiMakeDegradedBridgeFunction(self);
        }
        SCValdiMarshallerCheck(marshaller);
        return [objectRegistry unmarshallObjectOfClass:self fromMarshaller:marshaller atIndex:objectIndex];
    })
}

+ (nullable instancetype)resolveFunctionWithJSRuntime:(id<SCValdiJSRuntime>)jsRuntime error:(NSError **)error
{
    if ([self asyncStrictMode]) {
        NSAssert(![NSThread isMainThread],
                 @"When async_strict_mode is enabled, function resolution (resolveFunctionWithJSRuntime:error:) must not be called from the main thread (to avoid ANRs). Use a background thread, the JS thread, or invokeWithJSRuntimeProvider:completionHandler:.");
    }
    @try {
        // Non-degrading raising resolution: the safe resolver must report a teardown as nil+error to
        // its adopters (so they run their own degrade), not degrade to a no-op the way the raising
        // functionWithJSRuntime: does.
        return SCValdiMakeBridgeFunctionFromJSRuntime(self, jsRuntime, [self modulePath]);
    } @catch (SCValdiError *exception) {
        // Resolution legitimately fails when the JS runtime has been torn down (e.g. logout) while
        // a caller is still active. Swift cannot catch the NSException, so convert it here.
        if (error != NULL) {
            NSString *reason = exception.reason ?: exception.name;
            *error = [NSError errorWithDomain:SCValdiBridgeFunctionErrorDomain
                                         code:1
                                     userInfo:@{NSLocalizedDescriptionKey : reason}];
        }
        return nil;
    }
}

@end

// Raising resolver: raises an SCValdiError on any resolution failure (including teardown). The
// non-raising resolveFunctionWithJSRuntime:error: wraps this and reports nil+error. The teardown
// degrade lives in the raising public entry point functionWithJSRuntime:, not here.
id SCValdiMakeBridgeFunctionFromJSRuntime(Class objectClass,
                                             id<SCValdiJSRuntime> jsRuntime,
                                             NSString *path) {
    SCValdiMarshallerScoped(marshaller, {
        SCValdiMarshallableObjectRegistry *objectRegistry = SCValdiMarshallableObjectRegistryGetSharedInstance();
        [objectRegistry setSchemaOfClass:objectClass inMarshaller:marshaller];
        NSInteger objectIndex = [jsRuntime pushModuleAthPath:path inMarshaller:marshaller];
        SCValdiMarshallerCheck(marshaller);

        return [objectRegistry unmarshallObjectOfClass:objectClass fromMarshaller:marshaller atIndex:objectIndex];
    })
}
