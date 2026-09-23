package com.snap.valdi.callable

import java.lang.reflect.Method
import java.lang.reflect.Proxy
import org.junit.jupiter.api.Assertions.assertArrayEquals
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertSame
import org.junit.jupiter.api.Test

internal class ValdiFunctionTrampolineTest {

    @Test
    fun resolvesAndInvokesEverySupportedArity() {
        val entries = ValdiFunctionTrampoline.getFunctionClasses()
        assertEquals(17 * 5, entries.size)

        for (arity in 0..16) {
            val offset = arity * 5
            val functionClass = entries[offset + 1] as Class<*>
            val method = entries[offset + 3] as Method
            val arguments = Array<Any>(arity) { Any() }
            val result = Any()
            var invocationCount = 0

            assertEquals("kotlin.jvm.functions.Function$arity", entries[offset])
            assertSame(functionClass, method.declaringClass)
            assertEquals("invoke", method.name)
            assertEquals(Object::class.java, method.returnType)

            val function = Proxy.newProxyInstance(
                functionClass.classLoader,
                arrayOf(functionClass),
            ) { _, invokedMethod, receivedArguments ->
                assertEquals(method, invokedMethod)
                assertArrayEquals(arguments, receivedArguments ?: emptyArray<Any>())
                invocationCount++
                result
            }

            assertSame(result, method.invoke(function, *arguments))
            assertEquals(1, invocationCount)
        }
    }
}
