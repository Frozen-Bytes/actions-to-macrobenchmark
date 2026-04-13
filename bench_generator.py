import argparse
import os
import json
import sys


# ---------------------------------------------------------------------------
# CLI arguments
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate Kotlin macrobenchmark files from an AI-recorded actions JSON.\n"
            "If --actions-file is omitted, only the startup benchmark is written."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Packages
    parser.add_argument(
        "--package-name",
        default="com.google.samples.apps.nowinandroid.macrobenchmark",
        help="Benchmark module package name.",
    )
    parser.add_argument(
        "--target-package-name",
        default="com.google.samples.apps.nowinandroid",
        help="Package name of the app under test.",
    )

    # I/O
    parser.add_argument(
        "--actions-file",
        default=None,
        metavar="PATH",
        help="Path to the AI-recorded actions JSON. Omit to generate only the startup benchmark.",
    )

    parser.add_argument(
        "--output-dir",
        default="benchmarks/src/main/java/com/google/samples/apps/nowinandroid/macrobenchmark",
        metavar="DIR",
        help="Directory where the generated .kt files will be written.",
    )

    # UI
    parser.add_argument("--ui-timeout-ms", type=int, default=5000)

    # Screen dimensions
    parser.add_argument("--original-screen-width",  type=float, default=1000.0)
    parser.add_argument("--original-screen-height", type=float, default=1000.0)

    # Startup benchmark
    parser.add_argument("--skip-startup", action="store_true", help="Pass this flag to skip generating the startup benchmark.")
    parser.add_argument("--startup-warmup-iterations", type=int, default=1)
    parser.add_argument("--startup-iterations",        type=int, default=10)
    parser.add_argument("--startup-file-name", default="GeneratedStartupBenchmark.kt")

    # Frame-timing benchmark
    parser.add_argument("--frame-warmup-iterations", type=int, default=3)
    parser.add_argument("--frame-iterations",        type=int, default=10)
    parser.add_argument("--frame-file-name", default="GeneratedFrameTimingBenchmark.kt")

    # Memory benchmark
    parser.add_argument("--memory-warmup-iterations", type=int, default=3)
    parser.add_argument("--memory-iterations",        type=int, default=10)
    parser.add_argument("--memory-file-name", default="GeneratedMemoryUsageBenchmark.kt")

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Coordinate scaling
# ---------------------------------------------------------------------------

def make_scalers(orig_width: float, orig_height: float):
    def scale_x(x) -> str:
        return f"(({float(x)}f / {orig_width}f) * device.displayWidth).toInt()"

    def scale_y(y) -> str:
        return f"(({float(y)}f / {orig_height}f) * device.displayHeight).toInt()"

    return scale_x, scale_y


# ---------------------------------------------------------------------------
# Shell-text escaping
# ---------------------------------------------------------------------------

def escape_shell_text(text: str) -> str:
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    for ch in ["'", "`", "$", "!", "&", "|", ";", "<", ">", "(", ")", "{", "}"]:
        text = text.replace(ch, f"\\{ch}")
    text = text.replace(" ", "%s")
    return text


# ---------------------------------------------------------------------------
# Action -> Kotlin
# ---------------------------------------------------------------------------

def action_to_kotlin(action: dict, scale_x, scale_y) -> str:
    t = action.get("action_type")
    if not t:
        raise ValueError(f"Action is missing 'action_type': {action}")
    t = t.upper()

    if t in ("AWAKE", "COMPLETE", "ABORT", "INFO"):
        return f"// ACTION: {t}"

    elif t == "CLICK":
        if not action.get("point"):
            raise ValueError(f"Missing 'point' in CLICK action: {action}")
        x, y = action["point"]
        return f"device.click({scale_x(x)}, {scale_y(y)})"

    elif t == "LONGPRESS":
        if not action.get("point"):
            raise ValueError(f"Missing 'point' in LONGPRESS action: {action}")
        if "duration" not in action:
            raise ValueError(f"Missing 'duration' in LONGPRESS action: {action}")

        x, y = action["point"]
        duration_s = float(action["duration"])
        steps = max(1, int((duration_s * 1000) / 5))
        sx, sy = scale_x(x), scale_y(y)
        return f"device.swipe({sx}, {sy}, {sx}, {sy}, {steps}) // {duration_s}s long press"

    elif t == "TYPE":
        if "value" not in action:
            raise ValueError(f"Missing 'value' in TYPE action: {action}")
        commands = []
        point = action.get("point")
        if point:
            x, y = point
            commands.append(f"device.click({scale_x(x)}, {scale_y(y)})")
            commands.append("Thread.sleep(500L)")

        text = escape_shell_text(action["value"])
        commands.append(f'device.executeShellCommand("input text {text}")')
        return "\n        ".join(commands)

    elif t == "SLIDE":
        if "point1" not in action:
            raise ValueError(f"Missing 'point1' in SLIDE action: {action}")

        # Fallback for AI mistakes (using 'point' instead of 'point2')
        p2 = action.get("point2") or action.get("point")
        if not p2:
            raise ValueError(f"Missing 'point2' (or 'point') in SLIDE action: {action}")

        x1, y1 = action["point1"]
        x2, y2 = p2

        # Fallback for missing duration
        if "duration" not in action:
            print(f"[WARNING] Missing 'duration' in SLIDE action. Defaulting to 0.5s. Action: {action}", file=sys.stderr)
            duration_s = 0.1
        else:
            duration_s = float(action["duration"])

        steps = max(1, int((duration_s * 1000) / 5))
        return (
            f"device.swipe({scale_x(x1)}, {scale_y(y1)}, "
            f"{scale_x(x2)}, {scale_y(y2)}, {steps}) // {duration_s}s slide"
        )

    elif t == "WAIT":
        if "seconds" not in action:
            raise ValueError(f"Missing 'seconds' in WAIT action: {action}")
        return f"Thread.sleep({int(float(action['seconds']) * 1000)}L)"

    raise ValueError(f"Unknown action_type '{t}' in: {action}")


# ---------------------------------------------------------------------------
# Actions extraction
# ---------------------------------------------------------------------------

def extract_actions(file_path: str, scale_x, scale_y) -> list[str]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Actions file not found: '{file_path}'")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in '{file_path}': {e}")

    # Handle both direct lists and dicts containing "actions"
    if isinstance(data, list):
        actions_list = data
    elif isinstance(data, dict):
        actions_list = data.get("actions", [])
    else:
        raise ValueError(f"Unexpected JSON structure in '{file_path}'.")

    if not actions_list:
        raise ValueError(f"No actions found in '{file_path}'.")

    kotlin_lines: list[str] = []
    for i, action in enumerate(actions_list):
        try:
            line = action_to_kotlin(action, scale_x, scale_y)
        except ValueError as e:
            raise ValueError(f"Action #{i}: {e}") from None

        if line:
            kotlin_lines.append(line)

    return kotlin_lines


# ---------------------------------------------------------------------------
# Kotlin file generators
# ---------------------------------------------------------------------------

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
        setupBlock = {{
            pressHome()
        }},
    ) {{
        startActivityAndWait()
        device.waitForIdle()
        device.wait(Until.hasObject(By.pkg("{args.target_package_name}").depth(0)), {args.ui_timeout_ms}L)
    }}
}}
"""


def generate_action_benchmark(
    args: argparse.Namespace,
    class_name: str,
    metric: str,
    startup_mode: str,
    warmup_iters: int,
    iters: int,
    action_code: str,
    extra_annotations: list[str] | None = None,
) -> str:
    annotation_block = ""
    if extra_annotations:
        annotation_block = "\n".join(extra_annotations) + "\n"

    return get_imports(args.package_name) + f"""
{annotation_block}@RunWith(AndroidJUnit4::class)
class {class_name} {{
    @get:Rule
    val benchmarkRule = MacrobenchmarkRule()

    @Test
    fun measure() = benchmarkRule.measureRepeated(
        packageName = "{args.target_package_name}",
        metrics = listOf({metric}),
        startupMode = StartupMode.{startup_mode},
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


# ---------------------------------------------------------------------------
# File writing
# ---------------------------------------------------------------------------

def write_file(filepath: str, content: str) -> None:
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[generate_benchmarks] Written:  {filepath}")
    except OSError as e:
        print(f"[generate_benchmarks] ERROR writing '{filepath}': {e}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Startup benchmark
    # ------------------------------------------------------------------
    if args.skip_startup:
        print("[generate_benchmarks] Skipped generating Startup benchmark due to --skip-startup flag.")
    else:
        startup_path = os.path.join(args.output_dir, args.startup_file_name)
        write_file(startup_path, generate_startup_benchmark(args))

    # ------------------------------------------------------------------
    # Action-based benchmarks
    # ------------------------------------------------------------------
    if not args.actions_file:
        print(
            "[generate_benchmarks] No --actions-file provided. "
            "Frame and memory benchmarks were not generated."
        )
        return

    scale_x, scale_y = make_scalers(args.original_screen_width, args.original_screen_height)

    try:
        actions = extract_actions(args.actions_file, scale_x, scale_y)
    except (FileNotFoundError, ValueError) as e:
        print(f"[generate_benchmarks] ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if not actions:
        print(
            "[generate_benchmarks] WARNING: No executable actions found — "
            "the frame and memory benchmarks will measure an idle app.",
            file=sys.stderr,
        )

    action_code = "\n        ".join(actions)

    write_file(
        os.path.join(args.output_dir, args.frame_file_name),
        generate_action_benchmark(
            args,
            class_name="GeneratedFrameTimingBenchmark",
            metric="FrameTimingMetric()",
            startup_mode="WARM",
            warmup_iters=args.frame_warmup_iterations,
            iters=args.frame_iterations,
            action_code=action_code,
        ),
    )

    write_file(
        os.path.join(args.output_dir, args.memory_file_name),
        generate_action_benchmark(
            args,
            class_name="GeneratedMemoryUsageBenchmark",
            metric="MemoryUsageMetric(MemoryUsageMetric.Mode.Max)",
            startup_mode="WARM",
            warmup_iters=args.memory_warmup_iterations,
            iters=args.memory_iterations,
            action_code=action_code,
            extra_annotations=["@OptIn(ExperimentalMetricApi::class)"],
        ),
    )

    print(f"[generate_benchmarks] Done. Output: '{args.output_dir}/'")


if __name__ == "__main__":
    main()