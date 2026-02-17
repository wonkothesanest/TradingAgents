# Collection of items that I want done for this repo
* Have the capability to delete jobs from the queue.  This should just remove pending jobs, if the job is running try to kill the worker, wait for the job to be finished then delete the job. All other states should just remove the record of the job.
* Make sure the hkeys are all scoped to thsi projects prepend with "trading-goblin-trading-agents-*"
