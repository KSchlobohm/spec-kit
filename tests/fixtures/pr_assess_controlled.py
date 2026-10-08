"""Disposable controlled fixture for PR description assessment."""


def normalize_review_title(title: str) -> str:
    return " ".join(title.split()).lower()


if __name__ == "__main__":
    assert normalize_review_title("  Review TITLE  ") == "review title"
    assert normalize_review_title("Review\t\nTITLE") == "review title"
    assert normalize_review_title("review title") == "review title"
    assert normalize_review_title("") == ""
    assert normalize_review_title(" \t\n ") == ""
    print("Controlled fixture self-checks passed (5 cases).")
