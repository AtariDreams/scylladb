import requests

# api calls
def list_modules(rest_api):
    resp = rest_api.send("GET", "task_manager/list_modules")
    resp.raise_for_status()
    return resp.json()

def list_tasks(rest_api, module_name, internal=False, keyspace=None, table=None):
    args = { "internal": internal }
    if keyspace:
        args["keyspace"] = keyspace
    if table:
        args["table"] = table
    resp = rest_api.send("GET", f"task_manager/list_module_tasks/{module_name}", args)
    resp.raise_for_status()
    return resp.json()

def get_task_status(rest_api, task_id):
    resp = rest_api.send("GET", f"task_manager/task_status/{task_id}")
    resp.raise_for_status()
    return resp.json()

def abort_task(rest_api, task_id):
    resp = rest_api.send("POST", f"task_manager/abort_task/{task_id}")
    resp.raise_for_status()

def wait_for_task(rest_api, task_id):
    resp = rest_api.send("GET", f"task_manager/wait_task/{task_id}")
    resp.raise_for_status()
    return resp.json()

async def wait_for_task_async(rest_api, task_id):
    rest_api.send("GET", f"task_manager/wait_task/{task_id}")

def get_task_status_recursively(rest_api, task_id):
    resp = rest_api.send("GET", f"task_manager/task_status_recursive/{task_id}")
    resp.raise_for_status()
    return resp.json()

# helpers
def check_field_correctness(field_name, status, expected_status):
    if field_name in expected_status:
        assert status[field_name] == expected_status[field_name], f"Incorrect task {field_name}"

def check_status_correctness(status, expected_status):
    check_field_correctness("id", status, expected_status)
    check_field_correctness("state", status, expected_status)
    check_field_correctness("sequence_number", status, expected_status)
    check_field_correctness("keyspace", status, expected_status)
    check_field_correctness("table", status, expected_status)
    if "error" in expected_status:
        assert expected_status["error"] in status["error"], "Incorrect error message"
    else:
        assert status["error"] == "", "Error message was set"

def assert_task_does_not_exist(rest_api, task_id):
    resp = rest_api.send("GET", f"task_manager/task_status/{task_id}")
    assert resp.status_code == requests.codes.bad_request, f"Task {task_id} is kept in memory"

def check_child_parent_relationship(rest_api, parent, tree_depth, depth=0):
    assert parent["children_ids"], "Child tasks were not created"

    for child_id in parent["children_ids"]:
        child = wait_for_task(rest_api, child_id)
        assert parent["sequence_number"] == child["sequence_number"], f"Child task with id {child_id} did not inherit parent's sequence number"
        assert child["parent_id"] == parent["id"], f"Parent id of task with id {child_id} is not set"
        if depth + 1 < tree_depth:
            check_child_parent_relationship(rest_api, child, tree_depth, depth + 1)

def drain_module_tasks(rest_api, module_name):
    tasks = [task for task in list_tasks(rest_api, module_name, True)]
    for task in tasks:
        resp = rest_api.send("GET", f"task_manager/wait_task/{task['task_id']}")
        # The task may be already unregistered.
        assert resp.status_code == requests.codes.ok or resp.status_code == requests.codes.bad_request, "Invalid status code"
