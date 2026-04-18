from add import add


def test_positive_numbers():
    assert add(2, 3) == 5

def test_negative_numbers():
    assert add(-4, -6) == -10

def test_mixed_sign():
    assert add(-3, 7) == 4

def test_floats():
    assert add(1.5, 2.5) == 4.0

def test_zeros():
    assert add(0, 0) == 0

def test_large_numbers():
    assert add(1_000_000, 2_000_000) == 3_000_000

def test_three_numbers():
    assert add(1, 2, 3) == 6

def test_many_numbers():
    assert add(1, 2, 3, 4, 5) == 15

def test_single_number():
    assert add(7) == 7

def test_no_arguments():
    assert add() == 0
