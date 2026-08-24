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
    return SCValdiMakeBridgeFunctionFromJSRuntime(self, jsRuntime, [self modulePath]);
}

+ (nullable instancetype)resolveFunctionWithJSRuntime:(id<SCValdiJSRuntime>)jsRuntime error:(NSError **)error
{
    @try {
        return [self functionWithJSRuntime:jsRuntime];
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
