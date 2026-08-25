//
//  SCValdiBridgeInvocationErrorTests.m
//  ios_tests
//

#import <Foundation/Foundation.h>
#import <XCTest/XCTest.h>

#import "valdi/ios/SCValdiRuntimeManager.h"
#import "valdi_core/SCValdiError.h"
#import "valdi_core/SCValdiJSRuntime.h"
#import "valdi_core/SCValdiSharedLogger.h"

#import <SCCValdiTest/SCCValdiTest.h>

/// A synchronous JS throw during a bridged invocation must not cross the bridge as an SCValdiError
/// NSException: Swift callers cannot catch it (the process aborts below the Swift frame) and
/// unguarded Objective-C callers abort too. The bridge trampoline must instead report the error and
/// return a type-safe default value. See ios/swift/README.md.
@interface SCValdiBridgeInvocationErrorTests: XCTestCase

@property (strong, nonatomic) SCValdiRuntimeManager *runtimeManager;

@end

/// Captures every error-level log so the test can assert the degraded invocation was reported
/// rather than silently swallowed.
@interface SCValdiCapturingLogger: NSObject <SCValdiLogger>
@property (strong, nonatomic) NSMutableArray<NSString *> *errorLogs;
@end

@implementation SCValdiCapturingLogger

- (instancetype)init
{
    self = [super init];
    if (self) {
        _errorLogs = [NSMutableArray array];
    }
    return self;
}

- (BOOL)isLogEnabledForLevel:(SCValdiLoggerLevel)level
{
    return YES;
}

- (void)outputLog:(NSString *)log forLevel:(SCValdiLoggerLevel)level
{
    if (level == SCValdiLoggerLevelError) {
        @synchronized(self.errorLogs) {
            [self.errorLogs addObject:log];
        }
    }
}

@end

@implementation SCValdiBridgeInvocationErrorTests

- (void)setUp
{
    self.runtimeManager = [SCValdiRuntimeManager new];
    self.continueAfterFailure = NO;
}

- (void)tearDown
{
    self.runtimeManager = nil;
}

/// Resolves the FunctionTest fixture's ITestObject off the main thread (async_strict_mode forbids
/// resolution on the main thread) and hands it to the block.
- (void)withTestObject:(void (^)(id<SCCValdiTestITestObject> testObject))block
{
    XCTestExpectation *expectation = [self expectationWithDescription:@"test object resolved"];
    id<SCValdiRuntimeProtocol> runtime = self.runtimeManager.mainRuntime;
    XCTAssertNotNil(runtime);

    [SCCValdiTestMakeTestObject invokeWithJSRuntimeProvider:^id<SCValdiJSRuntime> {
        return [runtime jsRuntime];
    } completionHandler:^(id<SCCValdiTestITestObject> testObject) {
        XCTAssertNotNil(testObject);
        block(testObject);
        [expectation fulfill];
    }];

    [self waitForExpectations:@[expectation] timeout:5.0];
}

- (void)testSynchronousThrowDuringInvocationIsReportedNotRaised
{
    SCValdiCapturingLogger *logger = [SCValdiCapturingLogger new];
    id<SCValdiLogger> previousLogger = SCValdiGetSharedLogger();
    SCValdiSetSharedLogger(logger);

    @try {
        [self withTestObject:^(id<SCCValdiTestITestObject> testObject) {
            __block double result = 123.0;
            @try {
                result = [testObject throwSynchronously];
            } @catch (NSException *exception) {
                XCTFail(@"A synchronous JS throw must not raise across the bridge, got %@: %@",
                        exception.name, exception.reason);
                return;
            }

            // The crossing degraded to the type-safe default for a non-nullable `number` return.
            XCTAssertEqual(result, 0.0);

            // The failure must still be reported (logged), not silently swallowed.
            @synchronized(logger.errorLogs) {
                BOOL reported = NO;
                for (NSString *log in logger.errorLogs) {
                    if ([log containsString:@"throwSynchronously"]) {
                        reported = YES;
                        break;
                    }
                }
                XCTAssertTrue(reported, @"Expected the degraded invocation to be logged, got %@",
                              logger.errorLogs);
            }
        }];
    } @finally {
        SCValdiSetSharedLogger(previousLogger);
    }
}

- (void)testNonThrowingInvocationStillReturnsValue
{
    [self withTestObject:^(id<SCCValdiTestITestObject> testObject) {
        // Control: the fix must not disturb the normal, non-throwing invocation path.
        XCTAssertEqual([testObject addWithValue:10.0], 10.0);
        XCTAssertEqual([testObject addWithValue:32.0], 42.0);
    }];
}

@end
