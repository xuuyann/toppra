import pytest
import numpy as np
import numpy.testing as npt
import cvxpy

import toppra
import toppra.constraint as constraint
from toppra.solverwrapper import cvxpyWrapper, qpOASESSolverWrapper
from toppra.constants import TINY


@pytest.fixture(scope='class', params=['vel_accel'])
def pp_fixture(request):
    """ Velocity & Acceleration Path Constraint.

    This test case has only two constraints, one velocity constraint
    and one acceleration constraint.
    """
    dof = 6
    np.random.seed(1)  # Use the same randomly generated way pts
    way_pts = np.random.randn(4, dof) * 0.6
    N = 200
    path = toppra.SplineInterpolator(np.linspace(0, 1, 4), way_pts)
    ss = np.linspace(0, 1, N + 1)
    # Velocity Constraint
    vlim_ = np.random.rand(dof) * 10 + 10
    vlim = np.vstack((-vlim_, vlim_)).T
    pc_vel = constraint.JointVelocityConstraint(vlim)
    # Acceleration Constraints
    alim_ = np.random.rand(dof) * 10 + 100
    alim = np.vstack((-alim_, alim_)).T
    pc_acc = constraint.JointAccelerationConstraint(alim)

    pcs = [pc_vel, pc_acc]
    yield pcs, path, ss, vlim, alim

    print "\n [TearDown] Finish PP Fixture"


@pytest.mark.parametrize("solver_name", ['cvxpy', 'qpOASES'])
@pytest.mark.parametrize("i", [0, 10, 30])
@pytest.mark.parametrize("H", [np.array([[1.5, 0], [0, 1.0]]), np.zeros((2, 2)), None])
@pytest.mark.parametrize("g", [np.array([0.2, -1]), np.array([0.5, 1]), np.array([2.0, 1])])
@pytest.mark.parametrize("x_ineq", [(-1, 1), (0.2, 0.2), (0.4, 0.3), (None, None)])
def test_basic_init(pp_fixture, solver_name, i, H, g, x_ineq):
    """ A basic test case for wrappers.

    Notice that the input fixture `pp_fixture` is known to have two constraints,
    one velocity and one acceleration. Hence, in this test, I directly formulate
    an optimization with cvxpy to test the result.

    Parameters
    ----------
    pp_fixture: a fixture with only two constraints, one velocity and
        one acceleration constraint.

    """
    constraints, path, path_discretization, vlim, alim = pp_fixture
    if solver_name == "cvxpy":
        solver = cvxpyWrapper(constraints, path, path_discretization)
    elif solver_name == 'qpOASES':
        solver = qpOASESSolverWrapper(constraints, path, path_discretization)

    xmin, xmax = x_ineq
    xnext_min = 0
    xnext_max = 1
    
    # Algorithm
    result = solver.solve_stagewise_optim(i, H, g, xmin, xmax, xnext_min, xnext_max)
    
    # Actual result
    ux = cvxpy.Variable(2)
    u = ux[0]
    x = ux[1]
    _, _, _, _, _, _, xbound = solver.params[0]
    a, b, c, F, h, ubound, _ = solver.params[1]
    Di = path_discretization[i + 1] - path_discretization[i]
    v = a[i] * u + b[i] * x + c[i]
    cvxpy_constraints = [
        u <= ubound[i, 1],
        u >= ubound[i, 0],
        x <= xbound[i, 1],
        x >= xbound[i, 0],
        F[i] * v <= h[i],
        x + u * 2 * Di <= xnext_max,
        x + u * 2 * Di >= xnext_min,
    ]
    if xmin is not None:
        cvxpy_constraints.append(x <= xmax)
        cvxpy_constraints.append(x >= xmin)
    if H is not None:
        objective = cvxpy.Minimize(0.5 * cvxpy.quad_form(ux, H) + g * ux)
    else:
        objective = cvxpy.Minimize(g * ux)
    problem = cvxpy.Problem(objective, cvxpy_constraints)
    problem.solve(solver="MOSEK")
    if problem.status == "optimal":
        actual = np.array(ux.value).flatten()
    else:
        actual = [None, None]

    # Assertion
    if actual[0] is not None:
        npt.assert_allclose(result.flatten(), actual.flatten(), atol=5e-3, rtol=1e-5)  # Very bad accuracy? why?
    else:
        assert actual == result


