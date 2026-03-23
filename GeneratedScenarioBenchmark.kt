@file:OptIn(ExperimentalMetricApi::class)

package com.google.samples.apps.nowinandroid.interests // [INPUT REQUIRED]: Change this to your benchmark module's package name

import android.content.Intent
import androidx.benchmark.macro.BaselineProfileMode
import androidx.benchmark.macro.CompilationMode
import androidx.benchmark.macro.ExperimentalMetricApi
import androidx.benchmark.macro.FrameTimingMetric
import androidx.benchmark.macro.MemoryUsageMetric
import androidx.benchmark.macro.StartupMode
import androidx.benchmark.macro.StartupTimingMetric
import androidx.benchmark.macro.TraceSectionMetric
import androidx.benchmark.macro.junit4.MacrobenchmarkRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import org.json.JSONArray
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import com.google.samples.apps.nowinandroid.PACKAGE_NAME // this for now in android

// ==============================================================================
// CONFIGURATION & INPUTS
// ==============================================================================

/**
 * [INPUT REQUIRED]: Define the target application package name.
 */
private val TARGET_PACKAGE_NAME = PACKAGE_NAME

/**
 * [INPUT REQUIRED]: Define the JSON file name located in src/androidTest/assets/
 */
private const val ACTIONS_FILE_NAME = "actions.json"

/**
 * [INPUT REQUIRED]: Define maximum wait time (in milliseconds) for UI elements.
 */
private const val UI_TIMEOUT_MS = 5000L

// ==============================================================================
// CUSTOM METRICS
// ==============================================================================

object BaselineProfileMetrics {
    val jitCompilationMetric = TraceSectionMetric("JIT Compiling %", label = "JIT compilation")
    val classInitMetric = TraceSectionMetric("L%/%;", label = "ClassInit")
    val allStartupMetrics = listOf(StartupTimingMetric(), jitCompilationMetric, classInitMetric)
}


@RunWith(AndroidJUnit4::class)
class ScenarioBenchmarkTest {

    @get:Rule
    val benchmarkRule = MacrobenchmarkRule()

    private val actionsArray by lazy { loadActionsFromAssets() }

    // ----------- Helper: Load JSON from Assets -----------
    private fun loadActionsFromAssets(): JSONArray {
        val context = InstrumentationRegistry.getInstrumentation().context
        return try {
            val json = context.assets.open(ACTIONS_FILE_NAME).bufferedReader().use { it.readText() }
            JSONArray(json)
        } catch (e: Exception) {
            android.util.Log.e("Benchmark", "Failed to load $ACTIONS_FILE_NAME. Ensure it is in src/androidTest/assets/")
            JSONArray()
        }
    }

    // ----------- Helper: Execute JSON Actions -----------
    private fun executeActions(device: UiDevice, actions: JSONArray) {
        for (i in 0 until actions.length()) {
            val action = actions.getJSONObject(i)
            val type = action.getString("action_type")
            android.util.Log.d("Benchmark", "Executing action: $action")

            when (type) {
                "click" -> {
                    val x = action.getDouble("x")
                    val y = action.getDouble("y")
                    val xCalc = (device.displayWidth * x).toInt()
                    val yCalc = (device.displayHeight * y).toInt()
                    device.click(xCalc, yCalc)
                }
                "long_press" -> {
                    val x = action.getDouble("x")
                    val y = action.getDouble("y")
                    val xCalc = (device.displayWidth * x).toInt()
                    val yCalc = (device.displayHeight * y).toInt()
                    device.swipe(xCalc, yCalc, xCalc, yCalc, 100)
                }
                "scroll" -> {
                    when (action.optString("direction", "down")) {
                        "down" -> device.swipe(device.displayWidth / 2, (device.displayHeight * 0.8).toInt(), device.displayWidth / 2, (device.displayHeight * 0.2).toInt(), 20)
                        "up" -> device.swipe(device.displayWidth / 2, (device.displayHeight * 0.2).toInt(), device.displayWidth / 2, (device.displayHeight * 0.8).toInt(), 20)
                        "left" -> device.swipe((device.displayWidth * 0.8).toInt(), device.displayHeight / 2, (device.displayWidth * 0.2).toInt(), device.displayHeight / 2, 20)
                        "right" -> device.swipe((device.displayWidth * 0.2).toInt(), device.displayHeight / 2, (device.displayWidth * 0.8).toInt(), device.displayHeight / 2, 20)
                    }
                }
                "input_text" -> {
                    val text = action.getString("text").replace(" ", "%s")
                    device.executeShellCommand("input text '$text'")
                }
                "navigate_home" -> device.pressHome()
                "navigate_back" -> device.pressBack()
                "wait" -> Thread.sleep(1000) // [INPUT REQUIRED]: Adjust default wait time or skip the action
                "done" -> return
            }
            device.waitForIdle()
        }
    }

    // ----------- Test : STARTUP BENCHMARK (NO ACTIONS REQUIRED) -----------
    /**
     * General Startup Benchmark
     * - Works on any app
     * - Cold start
     * - Waits until device is idle and main window of app is visible
     */
    @Test
    fun startupTiming() = benchmarkRule.measureRepeated(
        packageName = TARGET_PACKAGE_NAME,
        metrics = listOf(StartupTimingMetric()), // Use BaselineProfileMetrics.allStartupMetrics if needed
        startupMode = StartupMode.COLD,
        compilationMode = CompilationMode.Partial(
            baselineProfileMode = BaselineProfileMode.Disable,
            warmupIterations = 1, // [INPUT REQUIRED]: Adjust warmup iterations if necessary
        ),
        iterations = 10, // [INPUT REQUIRED]: Adjust number of iterations for the test
        setupBlock = {
            val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
            // Ensure starting from home screen
            device.pressHome()
        },
    ) {
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())

        // Launch the app
        startActivityAndWait()

        // Wait until device is idle
        device.waitForIdle()

        // Wait until the app's main window is visible (general for any package)
        device.wait(Until.hasObject(By.pkg(TARGET_PACKAGE_NAME).depth(0)), UI_TIMEOUT_MS)
    }

    // ----------- Test: Frame Rendering (Jank Analysis) -----------
    @Test
    fun frameRenderingTiming() = benchmarkRule.measureRepeated(
        packageName = TARGET_PACKAGE_NAME,
        metrics = listOf(FrameTimingMetric()),
        startupMode = StartupMode.WARM,
        compilationMode = CompilationMode.Partial(
            baselineProfileMode = BaselineProfileMode.Disable,
            warmupIterations = 3 // [INPUT REQUIRED]
        ),
        iterations = 10, // [INPUT REQUIRED]
        setupBlock = {
            pressHome()
        }
    ) {
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())

        // Launch the app
        startActivityAndWait()

        // Wait until device is idle
        device.waitForIdle()

        // Wait until the app's main window is visible (general for any package)
        device.wait(Until.hasObject(By.pkg(TARGET_PACKAGE_NAME).depth(0)), UI_TIMEOUT_MS)

        executeActions(device, actionsArray)
    }

    // ----------- Test: Memory Usage -----------
    @Test
    fun memoryUsageMetric() = benchmarkRule.measureRepeated(
        packageName = TARGET_PACKAGE_NAME,
        metrics = listOf(MemoryUsageMetric(MemoryUsageMetric.Mode.Max)),
        startupMode = StartupMode.WARM,
        compilationMode = CompilationMode.Partial(
            baselineProfileMode = BaselineProfileMode.Disable,
            warmupIterations = 3 // [INPUT REQUIRED]
        ),
        iterations = 10, // [INPUT REQUIRED]
        setupBlock = {
            pressHome()
        }
    ) {
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())

        // Launch the app
        startActivityAndWait()

        // Wait until device is idle
        device.waitForIdle()

        // Wait until the app's main window is visible (general for any package)
        device.wait(Until.hasObject(By.pkg(TARGET_PACKAGE_NAME).depth(0)), UI_TIMEOUT_MS)

        executeActions(device, actionsArray)
    }
}