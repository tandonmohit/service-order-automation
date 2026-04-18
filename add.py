def add(*numbers):
    return sum(numbers)


if __name__ == "__main__":
    inputs = []
    print("Enter numbers one per line. Press Enter with no input to finish.")
    while True:
        val = input(f"Number {len(inputs) + 1}: ").strip()
        if val == "":
            break
        inputs.append(float(val))
    print(f"Result: {add(*inputs)}")
