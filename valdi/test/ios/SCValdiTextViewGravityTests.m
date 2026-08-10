#import <UIKit/UIKit.h>
#import <XCTest/XCTest.h>

#import "valdi/ios/Views/SCValdiTextView.h"

static NSUInteger const kLayoutPassCount = 5;

@interface SCValdiTextViewGravityTests : XCTestCase
@end

@implementation SCValdiTextViewGravityTests

- (UITextView *)editableTextViewIn:(SCValdiTextView *)view
{
    for (UIView *subview in view.subviews) {
        if ([subview isKindOfClass:UITextView.class]) {
            UITextView *textView = (UITextView *)subview;
            if (textView.editable && textView.userInteractionEnabled) {
                return textView;
            }
        }
    }
    return nil;
}

- (void)runLayoutPassesOn:(SCValdiTextView *)view
{
    for (NSUInteger i = 0; i < kLayoutPassCount; i++) {
        [view setNeedsLayout];
        [view layoutIfNeeded];
    }
}

// The center-gravity correction must not compound. The correction is written to
// textContainerInset.top, which feeds back into contentSize; recomputing from the polluted
// contentSize settled an empty text view at a third of the free space instead of centered.
- (void)testEmptyTextViewCentersAtSteadyState
{
    SCValdiTextView *view = [[SCValdiTextView alloc] initWithFrame:CGRectMake(0, 0, 300, 100)];
    UITextView *textView = [self editableTextViewIn:view];
    XCTAssertNotNil(textView);

    [self runLayoutPassesOn:view];

    UIEdgeInsets inset = textView.textContainerInset;
    CGFloat rawContentHeight = textView.contentSize.height - inset.top - inset.bottom;
    XCTAssertGreaterThan(rawContentHeight, 0.0, @"an empty text view still has a caret line of content");
    XCTAssertLessThan(rawContentHeight, 100.0, @"one caret line must not fill the whole view");

    CGFloat expectedTop = (100.0 - rawContentHeight) / 2.0;
    XCTAssertEqualWithAccuracy(inset.top, expectedTop, 1.0);
}

- (void)testEmptyTextViewInsetIsStableAcrossLayoutPasses
{
    SCValdiTextView *view = [[SCValdiTextView alloc] initWithFrame:CGRectMake(0, 0, 300, 100)];
    UITextView *textView = [self editableTextViewIn:view];
    XCTAssertNotNil(textView);

    [self runLayoutPassesOn:view];
    CGFloat settledTop = textView.textContainerInset.top;

    [self runLayoutPassesOn:view];
    XCTAssertEqualWithAccuracy(textView.textContainerInset.top, settledTop, 0.5);
}

- (void)testEmptyTextViewShorterThanContentClampsCorrectionToZero
{
    SCValdiTextView *view = [[SCValdiTextView alloc] initWithFrame:CGRectMake(0, 0, 300, 4)];
    UITextView *textView = [self editableTextViewIn:view];
    XCTAssertNotNil(textView);

    [self runLayoutPassesOn:view];

    XCTAssertEqualWithAccuracy(textView.textContainerInset.top, 0.0, 0.5);
}

// A stale contentSize read (inset already written, contentSize not yet refreshed) must not push
// the correction past the bounds; the stripped content height clamps at zero.
- (void)testStaleOversizedInsetRecoversToCenter
{
    SCValdiTextView *view = [[SCValdiTextView alloc] initWithFrame:CGRectMake(0, 0, 300, 100)];
    UITextView *textView = [self editableTextViewIn:view];
    XCTAssertNotNil(textView);

    [self runLayoutPassesOn:view];
    textView.textContainerInset = UIEdgeInsetsMake(500.0, 0, 0, 0);
    [self runLayoutPassesOn:view];

    UIEdgeInsets inset = textView.textContainerInset;
    XCTAssertLessThanOrEqual(inset.top, 100.0);

    CGFloat rawContentHeight = textView.contentSize.height - inset.top - inset.bottom;
    CGFloat expectedTop = (100.0 - rawContentHeight) / 2.0;
    XCTAssertEqualWithAccuracy(inset.top, expectedTop, 1.0);
}

@end
