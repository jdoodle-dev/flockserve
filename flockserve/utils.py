import pandas as pd

def time_weighted_mean(queue_tracker):
    """
    Calculate the time weighted mean of the queue length.
    :param queue_tracker:
    :return:
    """
    time_stamps = pd.Series(sorted(queue_tracker, reverse=True))
    total_time = time_stamps.max() - time_stamps.min()
    weights = (1 / total_time) * (time_stamps.max() - time_stamps)
    weights = weights / weights.sum() # normalize the weights
    queue_lengths = pd.Series(queue_tracker.values())
    return (weights * queue_lengths).sum() # calculate the weighted mean
