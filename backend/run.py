import os

from app import create_app

app = create_app()


def start_scheduler(flask_app):
    """In-process scheduler for single-instance deployments. Jobs are idempotent, so running one scheduler per
    process is safe; for multiple instances prefer `flask run-jobs` from cron on exactly one host."""
    from apscheduler.schedulers.background import BackgroundScheduler

    from app.tasks.jobs import run_all

    def job():
        with flask_app.app_context():
            run_all()

    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(job, "interval", minutes=flask_app.config["SCHEDULER_MINUTES"], id="maintenance",
                  max_instances=1, coalesce=True)
    sched.start()
    return sched


if __name__ == "__main__":
    # With the debug reloader the child process has WERKZEUG_RUN_MAIN set; start the scheduler only there.
    if app.config["SCHEDULER_ENABLED"] and os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_scheduler(app)
    app.run(debug=True, port=5000)
