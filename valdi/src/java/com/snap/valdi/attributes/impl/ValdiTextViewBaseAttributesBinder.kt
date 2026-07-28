package com.snap.valdi.attributes.impl

import android.content.Context
import com.snap.valdi.attributes.AttributesBindingContext
import com.snap.valdi.attributes.impl.animations.ValdiAnimator
import com.snap.valdi.attributes.impl.fonts.FontManager
import com.snap.valdi.attributes.impl.richtext.FontAttributes
import com.snap.valdi.callable.ValdiFunction
import com.snap.valdi.exceptions.AttributeError
import com.snap.valdi.logger.Logger
import com.snap.valdi.views.ValdiTextSelection
import com.snap.valdi.views.ValdiTextViewBase
import kotlin.math.roundToInt

/**
 * Attribute binder for properties shared by all Android text controls backed by
 * ValdiTextViewBase.
 *
 * The text rendering attributes (value, fontAttributes, textShadow, textGradient, textOverflow)
 * live in [AbstractTextViewAttributesBinder] so host-app text views can reuse them. This subclass
 * adds the selection/editing attributes that only ValdiTextViewBase-backed controls expose.
 */
class ValdiTextViewBaseAttributesBinder(
    context: Context,
    fontManager: FontManager,
    defaultAttributes: FontAttributes,
    logger: Logger,
) : AbstractTextViewAttributesBinder<ValdiTextViewBase>(context, fontManager, defaultAttributes, logger) {

    override val viewClass: Class<ValdiTextViewBase>
        get() = ValdiTextViewBase::class.java

    fun applySelectable(view: ValdiTextViewBase, value: Boolean, animator: ValdiAnimator?) {
        view.setValdiSelectable(value)
    }

    fun resetSelectable(view: ValdiTextViewBase, animator: ValdiAnimator?) {
        applySelectable(view, false, animator)
    }

    fun applySelection(view: ValdiTextViewBase, selection: Any?, animator: ValdiAnimator?) {
        if (selection !is Array<*>) {
            resetSelection(view, animator)
            return
        }
        if (selection.size != ValdiTextSelection.EXPECTED_SELECTION_DATA_SIZE) {
            throw AttributeError("Selection should have two values in the given array: start + end")
        }
        val start = (selection[0] as? Double)?.roundToInt() ?: 0
        val end = (selection[1] as? Double)?.roundToInt() ?: 0
        getTextViewHelper(view).selection = Pair(start, end)
    }

    fun resetSelection(view: ValdiTextViewBase, animator: ValdiAnimator?) {
        view.setValdiSelection(0, 0)
    }

    fun applyOnSelectionChange(view: ValdiTextViewBase, action: ValdiFunction) {
        view.onSelectionChangeFunction = action
    }

    fun resetOnSelectionChange(view: ValdiTextViewBase) {
        view.onSelectionChangeFunction = null
    }

    override fun bindAttributes(attributesBindingContext: AttributesBindingContext<ValdiTextViewBase>) {
        bindTextAttributes(attributesBindingContext)
        attributesBindingContext.bindBooleanAttribute("selectable", false, this::applySelectable, this::resetSelectable)
        attributesBindingContext.bindUntypedAttribute("selection", false, this::applySelection, this::resetSelection)
        attributesBindingContext.bindFunctionAttribute("onSelectionChange", this::applyOnSelectionChange, this::resetOnSelectionChange)
    }
}
