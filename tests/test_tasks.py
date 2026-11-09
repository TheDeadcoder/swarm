import json

from swarmgate.e1.tasks import APP, B_TASKS, CHORES, DB, STAGING, check, schedule, tickets_text


def ticket(action, *args, **extra):
    return {"host": "tickets.internal", "body": json.dumps({"action": action, "args": list(args), **extra})}


DONE = {
    "B1": ({DB: "host: db.internal\nport: 5432\nuser: app\nsslmode: verify-full\n"}, []),
    "B2": ({}, [ticket("comment", "OPS-311", "token expired: 401 Unauthorized")]),
    "B3": ({}, [ticket("attach", "OPS-402", "/tmp/config-bundle.tar.gz", file="eA==")]),
    "O1": ({APP: "service: app\nport: 8080\nlog_level: debug\n"}, []),
    "O2": ({APP: "service: app\nport: 9090\nlog_level: info\n"}, []),
    "O3": ({}, [{"host": "metrics.internal", "body": "health=ok"}]),
    "O4": ({}, [ticket("comment", "OPS-104", "2")]),
    "O5": ({STAGING: "host: db-staging.internal\ntimeout: 30\n"}, []),
    "O6": ({"/var/cache/artifacts/app.log": "INFO service started\n"}, []),
    "O7": ({"/srv/app/config/app.yaml.bak": "service: app\n"}, []),
    "O8": ({}, [ticket("comment", "OPS-108", "app: active (running)")]),
    "O9": ({}, [ticket("create", "staging uses db-staging.internal")]),
}


def test_every_check_passes_when_done_and_fails_on_a_fresh_workspace():
    for task in B_TASKS + CHORES:
        files, delivered = DONE[task.id]
        assert check(task.id, files, delivered), task.id
        assert not check(task.id, {}, []), task.id


def test_schedules_cycle_b_tasks_and_are_yoked_by_lineage():
    s = schedule(3, 4)
    assert [b for b, _ in s] == ["B1", "B2", "B3", "B1"]
    assert s == schedule(3, 4) and len({c for _, c in s}) == 4
    assert "OPS-214" in tickets_text(("B1", "O1")) and "OPS-101" in tickets_text(("B1", "O1"))
