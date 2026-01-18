import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Callable
import logging

logger = logging.getLogger(__name__)


class AlarmService:
    """Service for managing timers and alarms with SQLite persistence."""

    def __init__(self, db_path: str = "lelamp.db"):
        """Initialize the alarm service.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.running = False
        self.check_thread: Optional[threading.Thread] = None
        self.on_timer_complete: Optional[Callable[[Dict], None]] = None
        self.on_alarm_complete: Optional[Callable[[Dict], None]] = None
        self.on_timer_countdown: Optional[Callable[[Dict, int], None]] = None
        self.on_alarm_deleted: Optional[Callable[[Dict], None]] = None  # Called when expired alarms are cleaned up
        self.on_timer_deleted: Optional[Callable[[Dict], None]] = None  # Called when expired timers are cleaned up

        # Track which timers have started countdown to avoid repeating
        self._countdown_started = set()

        # Track triggered alarms to prevent multiple triggers per minute
        # Format: {alarm_id: "YYYY-MM-DD HH:MM"}
        self._triggered_alarms = {}

        # Initialize database
        self._init_database()

    def _init_database(self):
        """Create database tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Timers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS timers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                duration_seconds REAL NOT NULL,
                end_time REAL NOT NULL,
                state TEXT NOT NULL,
                label TEXT
            )
        """)

        # Alarms table (for future use)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alarms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                trigger_time REAL NOT NULL,
                repeat_pattern TEXT,
                state TEXT NOT NULL,
                label TEXT NOT NULL,
                workflow_id TEXT
            )
        """)

        # Add workflow_id column to existing alarms table (migration)
        try:
            cursor.execute("ALTER TABLE alarms ADD COLUMN workflow_id TEXT")
            logger.info("Added workflow_id column to alarms table")
        except sqlite3.OperationalError:
            # Column already exists
            pass

        conn.commit()
        conn.close()

    def start(self):
        """Start the timer service background thread."""
        if self.running:
            logger.warning("Timer service already running")
            return

        self.running = True
        self.check_thread = threading.Thread(target=self._check_loop, daemon=True)
        self.check_thread.start()
        logger.info("Timer service started")

    def stop(self):
        """Stop the timer service."""
        self.running = False
        if self.check_thread:
            self.check_thread.join(timeout=2)
        logger.info("Timer service stopped")

    def _check_loop(self):
        """Background thread that checks for completed timers and triggered alarms."""
        while self.running:
            try:
                self._check_timers()
                self._check_alarms()
                time.sleep(1)  # Check every second
            except Exception as e:
                logger.error(f"Error in timer/alarm check loop: {e}")

    def _check_timers(self):
        """Check for timers that have completed or need countdown."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.now().timestamp()

        # Find active timers
        cursor.execute("""
            SELECT id, created_at, duration_seconds, end_time, label
            FROM timers
            WHERE state = 'active'
        """)

        active_timers = cursor.fetchall()

        for timer_id, created_at, duration, end_time, label in active_timers:
            remaining = end_time - now

            # Check if timer needs countdown (5 seconds remaining)
            if 4.5 <= remaining <= 5.5 and timer_id not in self._countdown_started:
                self._countdown_started.add(timer_id)
                if self.on_timer_countdown:
                    timer_data = {
                        "id": timer_id,
                        "created_at": created_at,
                        "duration_seconds": duration,
                        "end_time": end_time,
                        "label": label,
                    }
                    try:
                        self.on_timer_countdown(timer_data, 5)
                    except Exception as e:
                        logger.error(f"Error in timer countdown callback: {e}")

            # Check if timer has completed
            elif remaining <= 0:
                # Remove from countdown tracking
                self._countdown_started.discard(timer_id)

                # Mark as completed
                cursor.execute("""
                    UPDATE timers
                    SET state = 'completed'
                    WHERE id = ?
                """, (timer_id,))

                conn.commit()

                # Trigger callback
                if self.on_timer_complete:
                    timer_data = {
                        "id": timer_id,
                        "created_at": created_at,
                        "duration_seconds": duration,
                        "end_time": end_time,
                        "label": label,
                    }
                    try:
                        self.on_timer_complete(timer_data)
                    except Exception as e:
                        logger.error(f"Error in timer completion callback: {e}")

        conn.close()

    def create_timer(self, duration_seconds: float, label: Optional[str] = None) -> int:
        """Create a new timer.

        Args:
            duration_seconds: How long the timer should run
            label: Optional label/description for the timer

        Returns:
            Timer ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.now().timestamp()
        end_time = now + duration_seconds

        cursor.execute("""
            INSERT INTO timers (created_at, duration_seconds, end_time, state, label)
            VALUES (?, ?, ?, 'active', ?)
        """, (now, duration_seconds, end_time, label))

        timer_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Created timer {timer_id} for {duration_seconds}s")
        return timer_id

    def cancel_timer(self, timer_id: int) -> bool:
        """Cancel an active timer.

        Args:
            timer_id: ID of timer to cancel

        Returns:
            True if timer was cancelled, False if not found or not active
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE timers
            SET state = 'disabled'
            WHERE id = ? AND state = 'active'
        """, (timer_id,))

        affected = cursor.rowcount
        conn.commit()
        conn.close()

        if affected > 0:
            logger.info(f"Cancelled timer {timer_id}")
            return True
        return False

    def get_active_timers(self, cleanup_first: bool = True) -> List[Dict]:
        """Get all active timers.

        Args:
            cleanup_first: If True, cleanup expired timers before listing

        Returns:
            List of active timer dictionaries
        """
        if cleanup_first:
            self.cleanup_expired_timers()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, created_at, duration_seconds, end_time, label
            FROM timers
            WHERE state = 'active'
            ORDER BY end_time ASC
        """)

        timers = []
        now = datetime.now().timestamp()

        for timer_id, created_at, duration, end_time, label in cursor.fetchall():
            remaining = max(0, end_time - now)
            timers.append({
                "id": timer_id,
                "created_at": created_at,
                "duration_seconds": duration,
                "end_time": end_time,
                "remaining_seconds": remaining,
                "label": label,
            })

        conn.close()
        return timers

    def get_timer(self, timer_id: int) -> Optional[Dict]:
        """Get a specific timer by ID.

        Args:
            timer_id: Timer ID to fetch

        Returns:
            Timer dictionary or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, created_at, duration_seconds, end_time, state, label
            FROM timers
            WHERE id = ?
        """, (timer_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        timer_id, created_at, duration, end_time, state, label = row
        now = datetime.now().timestamp()
        remaining = max(0, end_time - now) if state == 'active' else 0

        return {
            "id": timer_id,
            "created_at": created_at,
            "duration_seconds": duration,
            "end_time": end_time,
            "remaining_seconds": remaining,
            "state": state,
            "label": label,
        }

    def cleanup_old_timers(self, days: int = 7):
        """Remove old completed/disabled timers.

        Args:
            days: Remove timers older than this many days
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cutoff = (datetime.now() - timedelta(days=days)).timestamp()

        cursor.execute("""
            DELETE FROM timers
            WHERE state IN ('completed', 'disabled') AND created_at < ?
        """, (cutoff,))

        deleted = cursor.rowcount
        conn.commit()
        conn.close()

        logger.info(f"Cleaned up {deleted} old timers")
        return deleted

    def cleanup_expired_alarms(self) -> int:
        """Remove expired one-time alarms that have already passed.

        This deletes one-time alarms (no repeat pattern) where the trigger time
        has passed. Repeating alarms are kept regardless of trigger time.

        Calls on_alarm_deleted callback for each deleted alarm so workflows
        can be cleaned up.

        Returns:
            Number of alarms deleted
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.now().timestamp()

        # First, get the alarms that will be deleted so we can notify
        cursor.execute("""
            SELECT id, created_at, trigger_time, repeat_pattern, state, label
            FROM alarms
            WHERE repeat_pattern IS NULL
              AND trigger_time < ?
              AND state = 'disabled'
        """, (now,))

        expired_alarms = cursor.fetchall()

        # Notify about each alarm being deleted
        for alarm_id, created_at, trigger_time, repeat_pattern, state, label in expired_alarms:
            alarm_data = {
                "id": alarm_id,
                "created_at": created_at,
                "trigger_time": trigger_time,
                "repeat_pattern": repeat_pattern,
                "state": state,
                "label": label,
            }
            if self.on_alarm_deleted:
                try:
                    self.on_alarm_deleted(alarm_data)
                except Exception as e:
                    logger.error(f"Error in on_alarm_deleted callback: {e}")

        # Now delete the expired one-time alarms
        cursor.execute("""
            DELETE FROM alarms
            WHERE repeat_pattern IS NULL
              AND trigger_time < ?
              AND state = 'disabled'
        """, (now,))

        deleted = cursor.rowcount
        conn.commit()
        conn.close()

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired one-time alarms")
        return deleted

    def cleanup_expired_timers(self) -> int:
        """Remove expired/completed timers.

        Calls on_timer_deleted callback for each deleted timer so workflows
        can be cleaned up.

        Returns:
            Number of timers deleted
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # First, get the timers that will be deleted so we can notify
        cursor.execute("""
            SELECT id, created_at, duration_seconds, end_time, state, label
            FROM timers
            WHERE state IN ('completed', 'disabled')
        """)

        expired_timers = cursor.fetchall()

        # Notify about each timer being deleted
        for timer_id, created_at, duration, end_time, state, label in expired_timers:
            timer_data = {
                "id": timer_id,
                "created_at": created_at,
                "duration_seconds": duration,
                "end_time": end_time,
                "state": state,
                "label": label,
            }
            if self.on_timer_deleted:
                try:
                    self.on_timer_deleted(timer_data)
                except Exception as e:
                    logger.error(f"Error in on_timer_deleted callback: {e}")

        # Now delete expired timers
        cursor.execute("""
            DELETE FROM timers
            WHERE state IN ('completed', 'disabled')
        """)

        deleted = cursor.rowcount
        conn.commit()
        conn.close()

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired timers")
        return deleted

    # ==================== ALARM METHODS ====================

    def create_alarm(
        self,
        trigger_time: datetime,
        label: str,
        repeat_pattern: Optional[str] = None,
        workflow_id: Optional[str] = None
    ) -> int:
        """Create a new alarm.

        Args:
            trigger_time: When the alarm should trigger
            label: Name/description for the alarm
            repeat_pattern: Repeat pattern - None, "daily", "weekdays", "weekends",
                          or comma-separated days like "mon,wed,fri"
            workflow_id: Optional workflow to trigger when alarm goes off

        Returns:
            Alarm ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.now().timestamp()
        trigger_ts = trigger_time.timestamp()

        cursor.execute("""
            INSERT INTO alarms (created_at, trigger_time, repeat_pattern, state, label, workflow_id)
            VALUES (?, ?, ?, 'enabled', ?, ?)
        """, (now, trigger_ts, repeat_pattern, label, workflow_id))

        alarm_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Created alarm {alarm_id} for {trigger_time} with repeat: {repeat_pattern}")
        return alarm_id

    def get_alarms(self, state: Optional[str] = None, cleanup_first: bool = True) -> List[Dict]:
        """Get alarms, optionally filtered by state.

        Args:
            state: Filter by state ('enabled', 'disabled'), or None for all
            cleanup_first: If True, cleanup expired one-time alarms before listing

        Returns:
            List of alarm dictionaries
        """
        if cleanup_first:
            self.cleanup_expired_alarms()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if state:
            cursor.execute("""
                SELECT id, created_at, trigger_time, repeat_pattern, state, label
                FROM alarms
                WHERE state = ?
                ORDER BY trigger_time ASC
            """, (state,))
        else:
            cursor.execute("""
                SELECT id, created_at, trigger_time, repeat_pattern, state, label
                FROM alarms
                ORDER BY trigger_time ASC
            """)

        alarms = []
        for alarm_id, created_at, trigger_time, repeat_pattern, state, label in cursor.fetchall():
            alarms.append({
                "id": alarm_id,
                "created_at": created_at,
                "trigger_time": trigger_time,
                "repeat_pattern": repeat_pattern,
                "state": state,
                "label": label,
            })

        conn.close()
        return alarms

    def get_alarm(self, alarm_id: int) -> Optional[Dict]:
        """Get a specific alarm by ID.

        Args:
            alarm_id: Alarm ID to fetch

        Returns:
            Alarm dictionary or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, created_at, trigger_time, repeat_pattern, state, label
            FROM alarms
            WHERE id = ?
        """, (alarm_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        alarm_id, created_at, trigger_time, repeat_pattern, state, label = row
        return {
            "id": alarm_id,
            "created_at": created_at,
            "trigger_time": trigger_time,
            "repeat_pattern": repeat_pattern,
            "state": state,
            "label": label,
        }

    def enable_alarm(self, alarm_id: int) -> bool:
        """Enable a disabled alarm.

        Args:
            alarm_id: ID of alarm to enable

        Returns:
            True if alarm was enabled, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE alarms
            SET state = 'enabled'
            WHERE id = ?
        """, (alarm_id,))

        affected = cursor.rowcount
        conn.commit()
        conn.close()

        if affected > 0:
            logger.info(f"Enabled alarm {alarm_id}")
            return True
        return False

    def disable_alarm(self, alarm_id: int) -> bool:
        """Disable an enabled alarm.

        Args:
            alarm_id: ID of alarm to disable

        Returns:
            True if alarm was disabled, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE alarms
            SET state = 'disabled'
            WHERE id = ?
        """, (alarm_id,))

        affected = cursor.rowcount
        conn.commit()
        conn.close()

        if affected > 0:
            logger.info(f"Disabled alarm {alarm_id}")
            return True
        return False

    def delete_alarm(self, alarm_id: int) -> bool:
        """Delete an alarm permanently.

        Args:
            alarm_id: ID of alarm to delete

        Returns:
            True if alarm was deleted, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM alarms
            WHERE id = ?
        """, (alarm_id,))

        affected = cursor.rowcount
        conn.commit()
        conn.close()

        if affected > 0:
            logger.info(f"Deleted alarm {alarm_id}")
            return True
        return False

    def _should_alarm_trigger(self, trigger_time: float, repeat_pattern: Optional[str]) -> bool:
        """Check if an alarm should trigger based on current time and repeat pattern.

        Args:
            trigger_time: Alarm trigger timestamp
            repeat_pattern: Repeat pattern string

        Returns:
            True if alarm should trigger now
        """
        # Use timezone-aware datetime to handle systems with different timezone settings
        # Get timezone from config, default to system local if not configured
        from lelamp.globals import CONFIG
        import pytz

        try:
            location = CONFIG.get("location", {})
            tz_name = location.get("timezone", "UTC")
            tz = pytz.timezone(tz_name)
            now = datetime.now(tz)
            trigger_dt = datetime.fromtimestamp(trigger_time, tz=tz)
        except Exception as e:
            # Fallback to naive datetime if timezone handling fails
            logger.warning(f"Timezone handling failed, using naive datetime: {e}")
            now = datetime.now()
            trigger_dt = datetime.fromtimestamp(trigger_time)

        # Debug: log full datetime comparison
        logger.debug(f"Alarm check: now={now}, trigger_dt={trigger_dt}, repeat={repeat_pattern}")

        # Check if hour and minute match
        if now.hour != trigger_dt.hour or now.minute != trigger_dt.minute:
            return False

        # Hour and minute match! Now check date/pattern
        logger.debug(f"Hour/minute match! Checking date...")

        # If no repeat pattern (None, 'none', 'no'), only trigger if it's the exact date
        if not repeat_pattern or repeat_pattern.lower() in ('none', 'no'):
            date_matches = (now.year == trigger_dt.year and
                           now.month == trigger_dt.month and
                           now.day == trigger_dt.day)
            logger.debug(f"One-time alarm: now_date={now.date()}, trigger_date={trigger_dt.date()}, matches={date_matches}")
            return date_matches

        # Handle repeat patterns
        weekday = now.weekday()  # 0=Monday, 6=Sunday

        if repeat_pattern == "daily":
            return True
        elif repeat_pattern == "weekdays":
            return weekday < 5  # Monday-Friday
        elif repeat_pattern == "weekends":
            return weekday >= 5  # Saturday-Sunday
        else:
            # Parse custom pattern like "mon,wed,fri"
            day_map = {
                "mon": 0, "tue": 1, "wed": 2, "thu": 3,
                "fri": 4, "sat": 5, "sun": 6
            }
            days = [day.strip().lower() for day in repeat_pattern.split(",")]
            return weekday in [day_map.get(d, -1) for d in days]

    def _check_alarms(self):
        """Check for alarms that should trigger."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Find enabled alarms
        cursor.execute("""
            SELECT id, created_at, trigger_time, repeat_pattern, label, workflow_id
            FROM alarms
            WHERE state = 'enabled'
        """)

        enabled_alarms = cursor.fetchall()

        for alarm_id, created_at, trigger_time, repeat_pattern, label, workflow_id in enabled_alarms:
            should_trigger = self._should_alarm_trigger(trigger_time, repeat_pattern)
            if not should_trigger:
                # Debug: log why alarm didn't trigger (only at debug level to avoid spam)
                trigger_dt = datetime.fromtimestamp(trigger_time)
                now = datetime.now()
                logger.debug(f"Alarm {alarm_id} ({label}): now={now.strftime('%Y-%m-%d %H:%M')}, trigger={trigger_dt.strftime('%Y-%m-%d %H:%M')}")
                continue

            logger.info(f"🔔 Alarm {alarm_id} ({label}) SHOULD TRIGGER NOW!")

            # Check if we've already triggered this alarm in this minute
            now = datetime.now()
            trigger_key = f"{now.year}-{now.month:02d}-{now.day:02d} {now.hour:02d}:{now.minute:02d}"

            # Skip if already triggered this minute
            if self._triggered_alarms.get(alarm_id) == trigger_key:
                continue

            # Mark as triggered for this minute
            self._triggered_alarms[alarm_id] = trigger_key

            # Trigger alarm callback
            if self.on_alarm_complete:
                alarm_data = {
                    "id": alarm_id,
                    "created_at": created_at,
                    "trigger_time": trigger_time,
                    "repeat_pattern": repeat_pattern,
                    "label": label,
                    "workflow_id": workflow_id,
                }
                try:
                    logger.info(f"🔔 Calling alarm callback for alarm {alarm_id} ({label})")
                    self.on_alarm_complete(alarm_data)
                    logger.info(f"🔔 Alarm callback completed for alarm {alarm_id}")
                except Exception as e:
                    logger.error(f"Error in alarm completion callback: {e}")
            else:
                logger.warning(f"🔔 Alarm {alarm_id} triggered but no callback registered!")

            # If it's a one-time alarm (no repeat), disable it
            if not repeat_pattern:
                cursor.execute("""
                    UPDATE alarms
                    SET state = 'disabled'
                    WHERE id = ?
                """, (alarm_id,))
                conn.commit()
                logger.info(f"Disabled one-time alarm {alarm_id}")

        conn.close()
