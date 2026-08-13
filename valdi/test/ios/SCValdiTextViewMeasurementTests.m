#import <XCTest/XCTest.h>

#import "valdi/ios/Text/SCValdiFontAttributes.h"
#import "valdi/ios/Text/SCValdiTextLayout.h"
#import "valdi/ios/Views/SCValdiTextView.h"
#import "valdi_core/SCValdiFontManagerProtocol.h"

// Regression coverage for the live UITextView consuming backgroundEffectPadding as
// lineFragmentPadding (both horizontal sides) plus a vertical textContainerInset, so measurement
// must reserve the same space. Without the reserve, a text view sized to its measured width loses
// 2x padding of usable width and wraps one character per line (the SnapEditor bubble-wrap caption
// rendered vertically in the caption editor).
@interface SCValdiTextView (MeasurementTesting)
+ (CGSize)measureSizeWithMaxSize:(CGSize)maxSize
                   fontAttributes:(SCValdiFontAttributes *)fontAttributes
                      fontManager:(id<SCValdiFontManagerProtocol>)fontManager
                             text:(id)text
                      placeholder:(NSString *)placeholder
          backgroundEffectPadding:(CGFloat)backgroundEffectPadding
                  traitCollection:(UITraitCollection *)traitCollection;
@end

@interface SCValdiTextViewMeasurementTests : XCTestCase
@end

@implementation SCValdiTextViewMeasurementTests

static UITraitCollection *SCTestTraitCollection(void)
{
    return [UITraitCollection traitCollectionWithDisplayScale:2.0];
}

static SCValdiFontAttributes *SCTestFontAttributes(void)
{
    NSMutableDictionary<NSAttributedStringKey, id> *attributes = [NSMutableDictionary new];
    attributes[NSFontAttributeName] = [UIFont systemFontOfSize:28];
    return [[SCValdiFontAttributes alloc] initWithAttributes:attributes
                                                       font:nil
                                                      color:[UIColor blackColor]
                                               textAligment:NSTextAlignmentCenter
                                              numberOfLines:0
                                              lineBreakMode:NSLineBreakByWordWrapping
                                       needAttributedString:NO];
}

static CGSize SCTestMeasure(NSString *text, CGSize maxSize, CGFloat backgroundEffectPadding)
{
    return [SCValdiTextView measureSizeWithMaxSize:maxSize
                                    fontAttributes:SCTestFontAttributes()
                                       fontManager:nil
                                              text:text
                                       placeholder:nil
                           backgroundEffectPadding:backgroundEffectPadding
                                   traitCollection:SCTestTraitCollection()];
}

- (void)testBackgroundEffectPaddingIsReservedInMeasuredSize
{
    const CGFloat padding = 10.0;
    const CGSize maxSize = CGSizeMake(400.0, CGFLOAT_MAX);

    CGSize withoutPadding = SCTestMeasure(@"test", maxSize, 0.0);
    CGSize withPadding = SCTestMeasure(@"test", maxSize, padding);

    XCTAssertEqualWithAccuracy(withPadding.width,
                               withoutPadding.width + padding * 2.0,
                               0.5,
                               @"Measured width must reserve lineFragmentPadding on both sides");
    XCTAssertEqualWithAccuracy(withPadding.height,
                               withoutPadding.height + padding,
                               0.5,
                               @"Measured height must reserve the vertical textContainerInset");
}

- (void)testUsableWidthAtMeasuredSizeFitsTextOnOneLine
{
    const CGFloat padding = 10.0;
    const CGSize maxSize = CGSizeMake(400.0, CGFLOAT_MAX);

    CGSize rawTextSize = SCTestMeasure(@"test", maxSize, 0.0);
    CGSize measured = SCTestMeasure(@"test", maxSize, padding);

    // The live text container gets (measured width - 2x padding) of usable width; if that is
    // narrower than the text itself, a hugging text view re-wraps and renders vertically.
    XCTAssertGreaterThanOrEqual(measured.width - padding * 2.0 + 0.5,
                                rawTextSize.width,
                                @"Usable width at the measured size must still fit the text");
}

- (void)testConstrainedMeasureReservesPaddingFromAvailableSpace
{
    const CGFloat padding = 10.0;
    const CGSize maxSize = CGSizeMake(120.0, 200.0);
    NSString *text = @"a longer caption that has to wrap across lines";

    CGSize padded = SCTestMeasure(text, maxSize, padding);
    CGSize reduced = SCTestMeasure(text, CGSizeMake(maxSize.width - padding * 2.0, maxSize.height - padding), 0.0);

    XCTAssertEqualWithAccuracy(padded.width, reduced.width + padding * 2.0, 0.5);
    XCTAssertEqualWithAccuracy(padded.height, reduced.height + padding, 0.5);
}

- (void)testZeroPaddingMatchesRawTextLayoutMeasurement
{
    const CGSize maxSize = CGSizeMake(400.0, CGFLOAT_MAX);

    CGSize viaTextView = SCTestMeasure(@"test", maxSize, 0.0);
    CGSize viaTextLayout = [SCValdiTextLayout measureSizeWithMaxSize:maxSize
                                                      fontAttributes:SCTestFontAttributes()
                                                         fontManager:nil
                                                                text:@"test"
                                                     traitCollection:SCTestTraitCollection()];

    XCTAssertEqualWithAccuracy(viaTextView.width, viaTextLayout.width, 0.5);
    XCTAssertEqualWithAccuracy(viaTextView.height, viaTextLayout.height, 0.5);
}

@end
