//
//  JavaScriptTaskScheduler.hpp
//  valdi
//
//  Created by Simon Corsin on 5/12/21.
//

#pragma once

#include "valdi/runtime/Context/Context.hpp"
#include "valdi/runtime/Interfaces/IJavaScriptContext.hpp"
#include "valdi/runtime/JavaScript/JavaScriptCapturedStacktrace.hpp"
#include "valdi_core/cpp/Utils/Function.hpp"
#include "valdi_core/cpp/Utils/Shared.hpp"

#include <string>
#include <vector>

namespace Valdi {

struct JavaScriptEntryParameters {
    IJavaScriptContext& jsContext;
    JSExceptionTracker& exceptionTracker;
    const Ref<Context>& valdiContext;

    JavaScriptEntryParameters(IJavaScriptContext& jsContext,
                              JSExceptionTracker& exceptionTracker,
                              const Ref<Context>& valdiContext);
    ~JavaScriptEntryParameters();
};

struct JavaScriptThreadTask : public Valdi::Function<void(JavaScriptEntryParameters&)> {
    using Valdi::Function<void(JavaScriptEntryParameters&)>::Function;
};

enum JavaScriptTaskScheduleType {
    // Will be sync if the JS thread is current or the call is made
    // from the main thread and a main thread batch is current, async otherwise
    JavaScriptTaskScheduleTypeDefault,
    // Will always be sync
    JavaScriptTaskScheduleTypeAlwaysSync,
    // Will always be async
    JavaScriptTaskScheduleTypeAlwaysAsync,
};

class JavaScriptTaskScheduler : public SharedPtrRefCountable {
public:
    virtual void dispatchOnJsThread(Ref<Context> ownerContext,
                                    JavaScriptTaskScheduleType scheduleType,
                                    uint32_t delayMs,
                                    JavaScriptThreadTask&& function) = 0;
    virtual bool isInJsThread() = 0;

    inline void dispatchOnJsThreadAsync(Ref<Context> ownerContext, JavaScriptThreadTask&& function) {
        dispatchOnJsThread(std::move(ownerContext), JavaScriptTaskScheduleTypeDefault, 0, std::move(function));
    }

    inline void dispatchOnJsThreadAsyncAfter(Ref<Context> ownerContext,
                                             uint32_t delayMs,
                                             JavaScriptThreadTask&& function) {
        dispatchOnJsThread(
            std::move(ownerContext), JavaScriptTaskScheduleTypeAlwaysAsync, delayMs, std::move(function));
    }

    inline void dispatchOnJsThreadSync(Ref<Context> ownerContext, JavaScriptThreadTask&& function) {
        dispatchOnJsThread(std::move(ownerContext), JavaScriptTaskScheduleTypeAlwaysSync, 0, std::move(function));
    }

    virtual bool isDisposed() const {
        return false;
    }

    virtual Ref<Context> getLastDispatchedContext() const = 0;

    /**
     Capture the stacktraces of all running threads.
     The timeout parameter specifies how long the runtime will wait to get an interrupt
     handler called in order to capture the stacktraces.
     */
    virtual std::vector<JavaScriptCapturedStacktrace> captureStackTraces(
        std::chrono::steady_clock::duration timeout) = 0;

    // Extra attribution for ANR messages (" [stuck-in: <native call>] [module: <module>]"), or empty
    // if unavailable or ANR diagnostics are off. Reads saved native state without running JS, so it
    // is safe to call while the JS thread is stuck.
    virtual std::string getANRAttributionInfo() const {
        return {};
    }

    /**
     Whether the scheduler is far enough along in its lifecycle for unresponsiveness to be
     reported as an ANR. Runtime bootstrap (JS context creation plus core bundle evaluation)
     legitimately occupies the JS thread past the detection threshold on slow devices, so the
     detector excludes that window from ANR accounting. Must be safe to call from any thread
     while the JS thread is busy.
     */
    virtual bool isReadyForANRDetection() const {
        return true;
    }

    /**
     Bundle name of the JS module currently being loaded on the JS thread (the innermost of
     nested loads), or empty when no load is in flight. Module evaluation runs under the global
     context — which has no bundle name — and no JS stack exists yet while a bundle is being
     parsed, so an ANR that fires mid-load cannot be attributed from the captured stacktraces.
     The detector uses this as the fallback attribution. Must be safe to call from any thread
     while the JS thread is busy.
     */
    virtual StringBox getCurrentlyLoadingModule() const {
        return {};
    }
};

} // namespace Valdi
