import json
import os

# ==============================================================================
# CONFIGURATION
# ==============================================================================
PACKAGE_NAME = "com.google.samples.apps.nowinandroid.macrobenchmark" # Package name for the generated test files
TARGET_PACKAGE_NAME = "com.google.samples.apps.nowinandroid" # Package name of the target application
ACTIONS_FILE = "actions.json" # Ensure this JSON file is in the same directory as the script

# ==============================================================================
# TRANSLATE JSON ACTIONS TO KOTLIN CODE
# ==============================================================================
def action_to_kotlin(action: dict) -> str:
    t = action.get("action_type")

    if t == "click":
        x = action.get("x", 0.5)
        y = action.get("y", 0.5)
        return f'device.click((device.displayWidth * {x}).toInt(), (device.displayHeight * {y}).toInt())'

    elif t == "long_press":
        x = action.get("x", 0.5)
        y = action.get("y", 0.5)
        # A long press is a swipe from the same point to itself
        # The last parameter (100) controls duration, ~100 steps ≈ ~1 second long press
        return f'device.swipe((device.displayWidth * {x}).toInt(), (device.displayHeight * {y}).toInt(), (device.displayWidth * {x}).toInt(), (device.displayHeight * {y}).toInt(), 100)'

    elif t == "input_text":
        # Escape spaces and quotes for adb shell input
        text = action.get("text", "").replace(" ", "%s").replace('"', '\\"')
        return f'device.executeShellCommand("input text \'{text}\'")'

    elif t == "scroll":
        direction = action.get("direction", "down")
        if direction == "down":
            return 'device.swipe(device.displayWidth / 2, (device.displayHeight * 0.8).toInt(), device.displayWidth / 2, (device.displayHeight * 0.2).toInt(), 20)'
        elif direction == "up":
            return 'device.swipe(device.displayWidth / 2, (device.displayHeight * 0.2).toInt(), device.displayWidth / 2, (device.displayHeight * 0.8).toInt(), 20)'
        elif direction == "left":
            return 'device.swipe((device.displayWidth * 0.8).toInt(), device.displayHeight / 2, (device.displayWidth * 0.2).toInt(), device.displayHeight / 2, 20)'
        elif direction == "right":
            return 'device.swipe((device.displayWidth * 0.2).toInt(), device.displayHeight / 2, (device.displayWidth * 0.8).toInt(), device.displayHeight / 2, 20)'

    elif t == "navigate_home":
        return "device.pressHome()"

    elif t == "navigate_back":
        return "device.pressBack()"

    elif t == "wait":
        duration_ms = int(action.get("duration", 1) * 1000)
        return f"Thread.sleep({duration_ms}L)"

    return "// Unknown action"

# ==============================================================================
# GENERATE BASE IMPORTS
# ==============================================================================
def get_imports_and_setup() -> str:
    return f"""package {PACKAGE_NAME}

import androidx.benchmark.macro.BaselineProfileMode
import androidx.benchmark.macro.CompilationMode
import androidx.benchmark.macro.ExperimentalMetricApi
import androidx.benchmark.macro.FrameTimingMetric
import androidx.benchmark.macro.MemoryUsageMetric
import androidx.benchmark.macro.StartupMode
import androidx.benchmark.macro.StartupTimingMetric
import androidx.benchmark.macro.junit4.MacrobenchmarkRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

private const val TARGET_PACKAGE_NAME = "{TARGET_PACKAGE_NAME}"
private const val UI_TIMEOUT_MS = 5000L
"""

# ==============================================================================
# FILE 1: STARTUP BENCHMARK
# ==============================================================================
def generate_startup_benchmark() -> str:
    return get_imports_and_setup() + """
@RunWith(AndroidJUnit4::class)
class GeneratedStartupBenchmark {
    @get:Rule
    val benchmarkRule = MacrobenchmarkRule()

    @Test
    fun startupTiming() = benchmarkRule.measureRepeated(
        packageName = TARGET_PACKAGE_NAME,
        metrics = listOf(StartupTimingMetric()),
        startupMode = StartupMode.COLD,
        compilationMode = CompilationMode.Partial(
            baselineProfileMode = BaselineProfileMode.Disable,
            warmupIterations = 1,
        ),
        iterations = 10,
        setupBlock = {
            val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
            device.pressHome()
        },
    ) {
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())

        // Launch the app
        startActivityAndWait()

        // Wait until device is idle and app window is visible
        device.waitForIdle()
        device.wait(Until.hasObject(By.pkg(TARGET_PACKAGE_NAME).depth(0)), UI_TIMEOUT_MS)
    }
}
"""

# ==============================================================================
# FILE 2: FRAME TIMING BENCHMARK
# ==============================================================================
def generate_frame_benchmark(action_code: str) -> str:
    return get_imports_and_setup() + f"""
@RunWith(AndroidJUnit4::class)
class GeneratedFrameTimingBenchmark {{
    @get:Rule
    val benchmarkRule = MacrobenchmarkRule()

    @Test
    fun frameRenderingTiming() = benchmarkRule.measureRepeated(
        packageName = TARGET_PACKAGE_NAME,
        metrics = listOf(FrameTimingMetric()),
        startupMode = StartupMode.WARM,
        compilationMode = CompilationMode.Partial(
            baselineProfileMode = BaselineProfileMode.Disable,
            warmupIterations = 3
        ),
        iterations = 10,
        setupBlock = {{
            val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
            device.pressHome()

            // Launch the app
            startActivityAndWait()

            // Wait until device is idle and app window is visible
            device.waitForIdle()
            device.wait(Until.hasObject(By.pkg(TARGET_PACKAGE_NAME).depth(0)), UI_TIMEOUT_MS)
        }}
    ) {{
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())

        // Execute JSON injected actions
        {action_code}
    }}
}}
"""

# ==============================================================================
# FILE 3: MEMORY USAGE BENCHMARK
# ==============================================================================
def generate_memory_benchmark(action_code: str) -> str:
    return get_imports_and_setup() + f"""
@OptIn(ExperimentalMetricApi::class)
@RunWith(AndroidJUnit4::class)
class GeneratedMemoryUsageBenchmark {{
    @get:Rule
    val benchmarkRule = MacrobenchmarkRule()

    @Test
    fun memoryUsageMetric() = benchmarkRule.measureRepeated(
        packageName = TARGET_PACKAGE_NAME,
        metrics = listOf(MemoryUsageMetric(MemoryUsageMetric.Mode.Max)),
        startupMode = StartupMode.WARM,
        compilationMode = CompilationMode.Partial(
            baselineProfileMode = BaselineProfileMode.Disable,
            warmupIterations = 3
        ),
        iterations = 10,
        setupBlock = {{
            val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
            device.pressHome()

            // Launch the app
            startActivityAndWait()

            // Wait until device is idle and app window is visible
            device.waitForIdle()
            device.wait(Until.hasObject(By.pkg(TARGET_PACKAGE_NAME).depth(0)), UI_TIMEOUT_MS)
        }}
    ) {{
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())

        // Execute JSON injected actions
        {action_code}
    }}
}}
"""

def main():
    if os.path.exists(ACTIONS_FILE):
        with open(ACTIONS_FILE, "r") as f:
            actions = json.load(f)
    else:
        print(f"Warning: '{ACTIONS_FILE}' not found. Using default placeholder actions.")
        actions = [
            {"action_type": "scroll", "direction": "down"},
            {"action_type": "wait", "duration": 1},
            {"action_type": "scroll", "direction": "up"}
        ]

    # Generate Kotlin action lines
    action_code = "\n        ".join(action_to_kotlin(a) for a in actions)

    # Output Files mapping
    output_files = {
        "GeneratedStartupBenchmark.kt": generate_startup_benchmark(),
        "GeneratedFrameTimingBenchmark.kt": generate_frame_benchmark(action_code),
        "GeneratedMemoryUsageBenchmark.kt": generate_memory_benchmark(action_code)
    }

    print("-" * 50)
    for filename, code in output_files.items():
        # Check if file exists to determine if we are overwriting or creating
        if os.path.exists(filename):
            status_msg = "Overwritten existing file"
        else:
            status_msg = "Created new file"

        # The "w" mode automatically creates the file if it doesn't exist,
        # and completely overwrites it if it does.
        with open(filename, "w", encoding="utf-8") as f:
            f.write(code)

        print(f"✅ {status_msg}: {filename}")
    print("-" * 50)

if __name__ == "__main__":
    main()
