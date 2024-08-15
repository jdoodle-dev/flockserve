import pandas as pd
from itertools import groupby
from thefuzz import fuzz


def redundant_code_validator(text, fuzz_ratio_threshold):
    sentences = text.split("\n")
    # print("len(sentences): ", len(sentences))
    filtered_sentences = []
    redundant_sentences = []
    sentence = sentences[0]
    other_sentences = sentences[1:]
    while len(other_sentences):
        # Check fuzzy match against all other sentences
        filtered_sentences.append(sentence)
        unique_sentences = []

        for other_sentence in other_sentences:
            ratio = fuzz.ratio(sentence, other_sentence)
            if ratio > fuzz_ratio_threshold:
                redundant_sentences.append(other_sentence)
            else:
                unique_sentences.append(other_sentence)
        if len(unique_sentences) == 0:
            break

        sentence = unique_sentences[0]
        other_sentences = unique_sentences[1:]
    filtered_summary = "\n".join(filtered_sentences)
    # print("filtered sentences count", len(filtered_sentences))
    # print("redundant sentences count", len(redundant_sentences))
    # print("unique sentences count", len(unique_sentences))
    if redundant_sentences:

        return filtered_summary, True
    else:
        return text, False


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


def truncate_repetition(text, threshold=2, item_len_threshold=3, level="char"):
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

        cluster = list(grouped_items)
        if len(cluster) <= threshold:
            new_items.extend(cluster)
        else:
            # Should repeating items must have at least item_len_threshold to be considered as a repetition
            if len(item) < item_len_threshold and level != "char":
                new_items.extend(cluster)
                continue
            # don't consider white spaces as words and let char_level check consider it as it would potenitaly have much larger threshold
            if level == "char" and item == "":
                new_items.extend(cluster)
                continue

            new_items.extend(cluster[:threshold])
            truncated = True
            break

    if level == "char":
        return "".join(new_items), truncated
    elif level == "word":
        return " ".join(new_items), truncated
    elif level == "sentence":
        return "\\n".join(new_items), truncated


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
