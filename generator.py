from typing import List, Dict

PACKAGE_NAME = "com.example.app"
TEST_CLASS_NAME = "GeneratedMacrobenchmark"
TEST_METHOD_NAME = "generatedBenchmark"


def action_to_kotlin(action: Dict) -> str:
    t = action.get("action_type")

    if t == "click":
        return f'device.click({action["x"]}, {action["y"]})'

    elif t == "input_text":
        # Escape quotes for Kotlin
        text = action["text"].replace('"', '\\"')
        return f'device.executeShellCommand("input text \\"{text}\\"")'

    elif t == "scroll":
        if action["direction"] == "up":
            return 'device.swipe(500, 1500, 500, 500, 10)'
        else:
            return 'device.swipe(500, 500, 500, 1500, 10)'

    elif t == "navigate_home":
        return "device.pressHome()"

    elif t == "wait":
        duration_ms = int(action.get("duration", 2) * 1000)
        return f"Thread.sleep({duration_ms})"

    return "// Unknown action"


def generate_macrobenchmark(actions: List[Dict]) -> str:
    action_code = "\n        ".join(
        action_to_kotlin(a) for a in actions
    )

    return f"""\
package com.example.benchmark

import androidx.benchmark.macro.FrameTimingMetric
import androidx.benchmark.macro.MemoryUsageMetric
import androidx.benchmark.macro.MacrobenchmarkRule
import androidx.benchmark.macro.StartupMode
import androidx.benchmark.macro.measureRepeated
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.uiautomator.UiDevice
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class {TEST_CLASS_NAME} {{

    @get:Rule
    val benchmarkRule = MacrobenchmarkRule()

    @Test
    fun {TEST_METHOD_NAME}() = benchmarkRule.measureRepeated(
        packageName = "{PACKAGE_NAME}",
        metrics = listOf(
            FrameTimingMetric(),
            MemoryUsageMetric()
        ),
        compilationMode = CompilationMode.Partial(),
        iterations = 5,
        startupMode = StartupMode.COLD
    ) {{

        device.waitForIdle()

        {action_code}

        device.waitForIdle()
    }}
}}
"""

actions = [
    {"action_type": "click", "x": 300, "y": 800},
    {"action_type": "wait", "duration": 1.5},
    {"action_type": "input_text", "text": "hello world"},
    {"action_type": "click", "x": 500, "y": 1200},
    {"action_type": "scroll", "direction": "up"},
    {"action_type": "scroll", "direction": "up"}
]

macrobenchmark = generate_macrobenchmark(actions)

with open("GeneratedMacrobenchmark.kt", "w") as f:
    f.write(macrobenchmark)