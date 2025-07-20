# Write me a function that multiplies two matrics with numpy
import numpy as np


def multiply_matrices(matrix1, matrix2):
    """
    Multiplies two matrices using NumPy.

    Parameters:
    matrix1 (np.ndarray): The first matrix.
    matrix2 (np.ndarray): The second matrix.

    Returns:
    np.ndarray: The product of the two matrices.
    """
    import numpy as np

    # Ensure that the number of columns in the first matrix is equal to the number of rows in the second matrix
    if matrix1.shape[1] != matrix2.shape[0]:
        raise ValueError(
            "The number of columns in the first matrix must be equal to the number of rows in the second matrix."
        )

    # Compute the matrix product
    product = np.dot(matrix1, matrix2)

    return product


# Example usage:
matrix1 = np.array([[1, 2], [3, 4]])
matrix2 = np.array([[5, 6], [7, 8]])

result = multiply_matrices(matrix1, matrix2)
print(result)
