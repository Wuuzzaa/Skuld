import time
import logging
from datetime import datetime
from src.util import log_memory_usage, MemoryMonitor
from src.send_alert import send_telegram_message

logger = logging.getLogger(__name__)

class PipelineMonitor:
    def __init__(self, mode="all"):
        self.mode = mode
        self.start_time = None
        self.results = {}
        self.memory_stats = {}
        self.parallel_duration = 0
        self.monitor = MemoryMonitor(interval=5.0)
        self.tasks_started = {}

    def start(self):
        self.start_time = time.time()
        self.monitor.start()

    def stop(self):
        self.monitor.stop()

    def set_parallel_duration(self, duration):
        self.parallel_duration = duration

    def run_task(self, task_name, func, *args, **kwargs):
        """Runs a task with timing and error handling, returning stats."""
        start = time.time()
        logger.info("#" * 80)
        logger.info(f"Starting: {task_name}")
        start_mem = log_memory_usage(f"[MEM] Start {task_name}: ")
        logger.info("#" * 80)

        try:
            result = func(*args, **kwargs)
            duration = int(time.time() - start)
            end_mem = log_memory_usage(f"[MEM] End {task_name}: ")

            mem_diff = 0
            peak_mem = 0
            if start_mem is not None and end_mem is not None:
                mem_diff = end_mem - start_mem
                peak_mem = end_mem
                logger.info(f"[MEM] {task_name} consumed: {mem_diff:+.2f} MB")

            logger.info(f"✓ {task_name} - Done - Runtime: {duration}s")
            return task_name, result, None, mem_diff, peak_mem, duration
        except Exception as e:
            duration = int(time.time() - start)
            log_memory_usage(f"[MEM] Fail {task_name}: ")
            logger.error(f"✗ {task_name} - Failed after {duration}s: {e}")
            return task_name, None, e, 0, 0, duration

    def record_result(self, task_name, result, error, mem_diff, peak_mem):
        self.results[task_name] = (result, error)
        self.memory_stats[task_name] = {"diff": mem_diff, "peak": peak_mem}

    def generate_report(self, success):
        end_time = time.time()
        total_duration = int(end_time - self.start_time) if self.start_time else 0
        
        lines = []
        lines.append(f"Total Runtime: {total_duration}s ({total_duration / 60:.1f} minutes)")
        
        if self.parallel_duration > 0:
            lines.append(f"Parallel Execution: {self.parallel_duration}s")
            # Estimated savings
            if self.results:
               lines.append(f"Time Saved: ~{(len(self.results) * 60 - self.parallel_duration)}s (estimated)")

        lines.append("")
        
        # Memory stats
        if self.memory_stats:
            sorted_mem = sorted(self.memory_stats.items(), key=lambda x: x[1]['peak'], reverse=True)
            max_peak_task = sorted_mem[0]
            lines.append(f"Highest Peak Memory: {max_peak_task[1]['peak']:.2f} MB ({max_peak_task[0]})")
        
        # Failures
        failed_tasks = [name for name, (_, error) in self.results.items() if error is not None]
        
        status_msg = ""
        if not success:
            abort_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            status_msg = f"✗ Pipeline ABORTED at {abort_time} after {total_duration}s"
            if failed_tasks:
                 lines.append(f"Failed tasks ({len(failed_tasks)}):")
                 for task in failed_tasks:
                    lines.append(f"- {task}")
        elif failed_tasks:
            status_msg = f"⚠ Pipeline finished with {len(failed_tasks)} failures in {total_duration}s"
            for task in failed_tasks:
                lines.append(f"- {task}")
        else:
            status_msg = f"✓ All tasks completed successfully in {total_duration}s"

        full_report = f"{status_msg}\n\n" + "\n".join(lines)
        return full_report, total_duration

    def send_telegram_summary(self, success):
        report, _ = self.generate_report(success)
        
        # Determine readable name for the mode
        mode_display = self.mode.replace("_", " ").title()
        if self.mode == "all":
            base_title = "SKULD Pipeline"
        else:
            base_title = f"SKULD Job: {mode_display}"

        # title logic
        if success:
            # Check for partial failures
            failed_tasks = [name for name, (_, error) in self.results.items() if error is not None]
            if failed_tasks:
                 title = f"{base_title}: Warning (Completed with Failures)"
            else:
                 title = f"{base_title}: Success"
        else:
            title = f"{base_title}: FAILED"

        send_telegram_message(title, report)
