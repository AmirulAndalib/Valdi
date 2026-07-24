package com.snap.valdi.test

import android.view.View
import com.snap.valdi.test.adapters.ValdiLegacyViewMatcherAdapter
import com.snap.valdi.test.matchers.ValdiRootViewMatcher
import org.hamcrest.Matcher

@Deprecated("Please migrate to the ValdiElementMatchers API which is compatible with SnapDrawing")
object ValdiViewMatchers {

    /**
     * Matches a View which has the given Composer attribute name and value.
     */
    @Deprecated("Please migrate to the ValdiElementMatchers API which is compatible with SnapDrawing")
    @JvmStatic
    fun <T> withValdiAttribute(attributeName: String, attributeValue: T) =
        adapt(ValdiElementMatchers.withValdiAttribute(attributeName, attributeValue))

    /**
     * Matches any Root View inflated from Composer.
     */
    @Deprecated("Please migrate to the ValdiElementMatchers API which is compatible with SnapDrawing")
    @JvmStatic
    fun withValdiRootView(): Matcher<View> {
        return ValdiRootViewMatcher()
    }

    /**
     * Matches any Composer View that has an accessibilityId attribute set to the given value
     */
    @Deprecated("Please migrate to the ValdiElementMatchers API which is compatible with SnapDrawing")
    @JvmStatic
    fun withAccessibilityId(accessibilityId: String) =
        adapt(ValdiElementMatchers.withAccessibilityId(accessibilityId))

    /**
     * Matches any Composer View that has an accessibilityId attribute value that matches the given prefix
     */
    @Deprecated("Please migrate to the ValdiElementMatchers API which is compatible with SnapDrawing")
    @JvmStatic
    fun withAccessibilityIdPrefix(accessibilityIdPrefix: String) =
        adapt(ValdiElementMatchers.withAccessibilityIdPrefix(accessibilityIdPrefix))

    @JvmStatic
    private fun adapt(matcher: Matcher<ValdiElementWithRootView>): Matcher<View> {
        return ValdiLegacyViewMatcherAdapter(matcher)
    }
}
