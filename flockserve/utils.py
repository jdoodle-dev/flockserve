import pandas as pd
from itertools import groupby


def time_weighted_mean(queue_tracker):
    """
    Calculate the time weighted mean of the queue length.
    :param queue_tracker:
    :return:
    """
    time_stamps = pd.Series(sorted(queue_tracker, reverse=True))
    total_time = time_stamps.max() - time_stamps.min()
    weights = (1 / total_time) * (time_stamps.max() - time_stamps)
    weights = weights / weights.sum()  # normalize the weights
    queue_lengths = pd.Series(queue_tracker.values())
    return (weights * queue_lengths).sum()  # calculate the weighted mean


def record_metrics(meters, records):
    for meter_name, value in records.items():
        if meter_name == "task_queue_meter":
            continue
        elif meter_name in meters.keys():
            meters[meter_name].record(value)
        else:
            continue


def truncate_repetition(text, threshold=2, level="char"):
    """
    Below is how the itertools.groupby behaves

    def groupby(iterable, key=None):
        # [k for k, g in groupby('AAAABBBCCDAABBB')] → A B C D A B
        # [list(g) for k, g in groupby('AAAABBBCCD')] → AAAA BBB CC D

    """

    if level == "char":
        items = list(text)
    elif level == "word":
        items = text.split(" ")
    elif level == "sentence":
        items = text.split("\\n")
        items = [item.strip() for item in items]
    else:
        raise ValueError

    new_items = []
    truncated = False
    for item, grouped_items in groupby(items):

        # don't consider white spaces as words and let char_level check consider it as it would potenitaly have much larger threshold
        if level != "char" and item == "":
            # break
            continue

        cluster = list(grouped_items)
        if len(cluster) <= threshold:
            new_items.extend(cluster)
        else:
            new_items.extend(cluster[:threshold])
            truncated = True
            break

    if level == "char":
        return "".join(new_items), truncated
    elif level == "word":
        return " ".join(new_items), truncated
    elif level == "sentence":
        return "\n".join(new_items), truncated


def frequency_based_truncate_repetition(text, threshold=5, level="char"):
    count_dict = {}
    raw_text = text

    if level == "char":
        items = list(text)
    elif level == "word":
        items = text.split(" ")

    elif level == "sentence":
        items = text.split("\\n")
    else:
        raise ValueError

    new_items = []
    # Update sentence counts
    for item in items:
        if level == "char":
            continue
        elif level == "word":
            new_items.append(item)
            stripped_item = item.strip()

            if item and len(stripped_item) > 2:
                count_dict[stripped_item] = count_dict.get(stripped_item, 0) + 1
                # Check if any sentence occurs more than threshold
                if count_dict[stripped_item] > threshold:
                    # Stop streaming
                    print(f"Stopping stream: {item}")
                    return " ".join(new_items), True

        elif level == "sentence":

            new_items.append(item)
            # print(new_items)
            stripped_item = item.strip()

            if item and len(stripped_item) > 10:
                count_dict[stripped_item] = count_dict.get(stripped_item, 0) + 1

                # Check if any sentence occurs more than threshold
                if count_dict[stripped_item] > threshold:
                    # Stop streaming
                    print(f"Stopping stream: {item}")
                    return "\n".join(new_items), True

    return raw_text, False
