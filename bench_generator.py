import argparse
import os
import json
import sys
import re

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Kotlin macrobenchmarks from AI JSON logs.")
    parser.add_argument("--package-name", default="com.google.samples.apps.nowinandroid.Generator")
    parser.add_argument("--target-package-name", default="com.google.samples.apps.nowinandroid.demo")
    parser.add_argument("--actions-dir", default="gelab-zero/running_log/action_logs")
    parser.add_argument("--output-dir", default="benchmarks/src/main/kotlin/com/google/samples/apps/nowinandroid/Generator")
    parser.add_argument("--ui-timeout-ms", type=int, default=5000)
    parser.add_argument("--smart-wait-ms", type=int, default=1000)
    parser.add_argument("--original-screen-width", type=float, default=1000.0)
    parser.add_argument("--original-screen-height", type=float, default=1000.0)
    parser.add_argument("--startup-warmup-iterations", type=int, default=1)
    parser.add_argument("--startup-iterations", type=int, default=10)
    parser.add_argument("--frame-warmup-iterations", type=int, default=3)
    parser.add_argument("--frame-iterations", type=int, default=10)
    parser.add_argument("--memory-warmup-iterations", type=int, default=3)
    parser.add_argument("--memory-iterations", type=int, default=10)
    return parser.parse_args()

def make_scalers(orig_width: float, orig_height: float):
    def scale_x(x) -> str:
        return f"(({float(x)}f / {orig_width}f) * device.displayWidth).toInt()"
    def scale_y(y) -> str:
        return f"(({float(y)}f / {orig_height}f) * device.displayHeight).toInt()"
    return scale_x, scale_y

def escape_shell_text(text: str) -> str:
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    for ch in ["'", "`", "$", "!", "&", "|", ";", "<", ">", "(", ")", "{", "}"]:
        text = text.replace(ch, f"\\{ch}")
    return text.replace(" ", "%s")

def action_to_kotlin(action: dict, scale_x, scale_y, smart_wait_ms: int) -> str:
    t = action.get("action_type", "").upper()
    smart_wait = f"device.waitForIdle()\n        Thread.sleep({smart_wait_ms}L)"

    if t in ("AWAKE", "COMPLETE", "ABORT", "INFO"):
        return f"// ACTION: {t}"
    elif t == "CLICK":
        x, y = action["point"]
        return f"device.click({scale_x(x)}, {scale_y(y)})\n        {smart_wait}"
    elif t == "LONGPRESS":
        x, y = action["point"]
        duration_s = float(action["duration"])
        steps = max(1, int((duration_s * 1000) / 5))
        return f"device.swipe({scale_x(x)}, {scale_y(y)}, {scale_x(x)}, {scale_y(y)}, {steps})\n        {smart_wait}"
    elif t == "TYPE":
        commands = []
        if "point" in action:
            x, y = action["point"]
            commands.extend([f"device.click({scale_x(x)}, {scale_y(y)})", smart_wait])
        commands.append(f'device.executeShellCommand("input text {escape_shell_text(action["value"])}")')
        commands.append(smart_wait)
        return "\n        ".join(commands)
    elif t == "SLIDE":
        x1, y1 = action["point1"]
        x2, y2 = action.get("point2", action.get("point"))
        duration_s = float(action.get("duration", 0.1))
        steps = max(1, int((duration_s * 1000) / 5))
        return f"device.swipe({scale_x(x1)}, {scale_y(y1)}, {scale_x(x2)}, {scale_y(y2)}, {steps})\n        {smart_wait}"
    elif t == "WAIT":
        return f"device.waitForIdle()\n        Thread.sleep({int(float(action['seconds']) * 1000)}L)"

    raise ValueError(f"Unknown action_type '{t}'")

def extract_actions(file_path: str, scale_x, scale_y, smart_wait_ms: int) -> list[str]:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    actions_list = data if isinstance(data, list) else data.get("actions", [])
    return [line for a in actions_list if (line := action_to_kotlin(a, scale_x, scale_y, smart_wait_ms))]

def get_imports(package_name: str) -> str:
    return f"""package {package_name}

import androidx.benchmark.macro.BaselineProfileMode
import androidx.benchmark.macro.CompilationMode
import androidx.benchmark.macro.ExperimentalMetricApi
import androidx.benchmark.macro.FrameTimingMetric
import androidx.benchmark.macro.MemoryUsageMetric
import androidx.benchmark.macro.StartupMode
import androidx.benchmark.macro.StartupTimingMetric
import androidx.benchmark.macro.junit4.MacrobenchmarkRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
"""

def generate_startup_benchmark(args: argparse.Namespace) -> str:
    return get_imports(args.package_name) + f"""
@RunWith(AndroidJUnit4::class)
class GeneratedStartupBenchmark {{
    @get:Rule
    val benchmarkRule = MacrobenchmarkRule()

    @Test
    fun measure() = benchmarkRule.measureRepeated(
        packageName = "{args.target_package_name}",
        metrics = listOf(StartupTimingMetric()),
        startupMode = StartupMode.COLD,
        compilationMode = CompilationMode.Partial(
            baselineProfileMode = BaselineProfileMode.Disable,
            warmupIterations = {args.startup_warmup_iterations},
        ),
        iterations = {args.startup_iterations},
        setupBlock = {{ pressHome() }},
    ) {{
        startActivityAndWait()
        device.waitForIdle()
        device.wait(Until.hasObject(By.pkg("{args.target_package_name}").depth(0)), {args.ui_timeout_ms}L)
    }}
}}
"""

def generate_action_benchmark(args, class_name, metric, iters, action_code, warmup_iters, annotations="") -> str:
    return get_imports(args.package_name) + f"""
{annotations}
@RunWith(AndroidJUnit4::class)
class {class_name} {{
    @get:Rule
    val benchmarkRule = MacrobenchmarkRule()

    @Test
    fun measure() = benchmarkRule.measureRepeated(
        packageName = "{args.target_package_name}",
        metrics = listOf({metric}),
        startupMode = StartupMode.WARM,
        compilationMode = CompilationMode.Partial(
            baselineProfileMode = BaselineProfileMode.Disable,
            warmupIterations = {warmup_iters},
        ),
        iterations = {iters},
        setupBlock = {{
            pressHome()
            startActivityAndWait()
            device.waitForIdle()
            device.wait(Until.hasObject(By.pkg("{args.target_package_name}").depth(0)), {args.ui_timeout_ms}L)
        }},
    ) {{
        {action_code}
    }}
}}
"""

def write_file(filepath: str, content: str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")

def main() -> None:
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    startup_filepath = os.path.join(args.output_dir, "GeneratedStartupBenchmark.kt")
    if not os.path.exists(startup_filepath):
        write_file(startup_filepath, generate_startup_benchmark(args))
        print(f"[INFO] Generated: {startup_filepath}")
    else:
        print(f"[INFO] Skipped: {startup_filepath} (Already exists)")

    if not os.path.exists(args.actions_dir):
        sys.exit(0)

    scale_x, scale_y = make_scalers(args.original_screen_width, args.original_screen_height)

    for filename in os.listdir(args.actions_dir):
        if not filename.endswith(".json"):
            continue

        filepath = os.path.join(args.actions_dir, filename)
        safe_name = re.sub(r'\W', '_', os.path.splitext(filename)[0])

        try:
            actions = extract_actions(filepath, scale_x, scale_y, args.smart_wait_ms)
            if not actions: continue

            action_code = "\n        ".join(actions)

            write_file(
                os.path.join(args.output_dir, f"GeneratedFrameTimingBenchmark_{safe_name}.kt"),
                generate_action_benchmark(args, f"GeneratedFrameTimingBenchmark_{safe_name}", "FrameTimingMetric()", args.frame_iterations, action_code, args.frame_warmup_iterations)
            )

            write_file(
                os.path.join(args.output_dir, f"GeneratedMemoryUsageBenchmark_{safe_name}.kt"),
                generate_action_benchmark(args, f"GeneratedMemoryUsageBenchmark_{safe_name}", "MemoryUsageMetric(MemoryUsageMetric.Mode.Max)", args.memory_iterations, action_code, args.memory_warmup_iterations, "@OptIn(ExperimentalMetricApi::class)")
            )
            print(f"[INFO] Generated benchmarks for: {filename}")
        except Exception as e:
            print(f"[ERROR] Failed to process {filename}: {e}")

if __name__ == "__main__":
    main()