"""Module for querying SymPy objects about assumptions."""
from sympy.core import sympify
from sympy.logic.boolalg import to_cnf, And, Not, Or, Implies, Equivalent
from sympy.logic.inference import satisfiable
from sympy.assumptions.assume import (global_assumptions, Predicate,
        AppliedPredicate)


class Q:
    """Supported ask keys."""
    antihermitian = Predicate('antihermitian')
    bounded = Predicate('bounded')
    commutative = Predicate('commutative')
    complex = Predicate('complex')
    composite = Predicate('composite')
    even = Predicate('even')
    extended_real = Predicate('extended_real')
    hermitian = Predicate('hermitian')
    imaginary = Predicate('imaginary')
    infinitesimal = Predicate('infinitesimal')
    infinity = Predicate('infinity')
    integer = Predicate('integer')
    irrational = Predicate('irrational')
    rational = Predicate('rational')
    negative = Predicate('negative')
    nonzero = Predicate('nonzero')
    positive = Predicate('positive')
    prime = Predicate('prime')
    real = Predicate('real')
    odd = Predicate('odd')
    is_true = Predicate('is_true')
    symmetric = Predicate('symmetric')
    invertible = Predicate('invertible')
    orthogonal = Predicate('orthogonal')
    positive_definite = Predicate('positive_definite')
    upper_triangular = Predicate('upper_triangular')
    lower_triangular = Predicate('lower_triangular')
    diagonal = Predicate('diagonal')


def _extract_facts(expr, symbol):
    """
    Helper for ask().

    Extracts the facts relevant to the symbol from an assumption.
    Returns None if there is nothing to extract.
    """
    if not expr.has(symbol):
        return None
    if isinstance(expr, AppliedPredicate):
        return expr.func
    return expr.func(*filter(lambda x: x is not None,
                [_extract_facts(arg, symbol) for arg in expr.args]))


def ask(proposition, assumptions=True, context=global_assumptions):
    """
    Method for inferring properties about objects.

    **Syntax**

        * ask(proposition)

        * ask(proposition, assumptions)

            where ``proposition`` is any boolean expression

    Examples
    ========

    >>> from sympy import ask, Q, pi
    >>> from sympy.abc import x, y
    >>> ask(Q.rational(pi))
    False
    >>> ask(Q.even(x*y), Q.even(x) & Q.integer(y))
    True
    >>> ask(Q.prime(x*y), Q.integer(x) &  Q.integer(y))
    False

    **Remarks**
        Relations in assumptions are not implemented (yet), so the following
        will not give a meaningful result.

        >>> ask(Q.positive(x), Q.is_true(x > 0)) # doctest: +SKIP

        It is however a work in progress.

    """
    assumptions = And(assumptions, And(*context))
    if isinstance(proposition, AppliedPredicate):
        key, expr = proposition.func, sympify(proposition.arg)
    else:
        key, expr = Q.is_true, sympify(proposition)

    # direct resolution method, no logic
    res = key(expr)._eval_ask(assumptions)
    if res is not None:
        return res

    if assumptions is True:
        return

    local_facts = _extract_facts(assumptions, expr)
    if local_facts is None or local_facts is True:
        return

    # See if there's a straight-forward conclusion we can make for the inference
    if local_facts.is_Atom:
        if key in known_facts_dict[local_facts]:
            return True
        if Not(key) in known_facts_dict[local_facts]:
            return False
    elif local_facts.func is And and all(k in known_facts_dict for k in local_facts.args):
        for assum in local_facts.args:
            if assum.is_Atom:
                if key in known_facts_dict[assum]:
                    return True
                if Not(key) in known_facts_dict[assum]:
                    return False
            elif assum.func is Not and assum.args[0].is_Atom:
                if key in known_facts_dict[assum]:
                    return False
                if Not(key) in known_facts_dict[assum]:
                    return True
    elif (isinstance(key, Predicate) and
            local_facts.func is Not and local_facts.args[0].is_Atom):
        if local_facts.args[0] in known_facts_dict[key]:
            return False

    # Failing all else, we do a full logical inference
    return ask_full_inference(key, local_facts, known_facts_cnf)


def ask_full_inference(proposition, assumptions, known_facts_cnf):
    """
    Method for inferring properties about objects.

    """
    if not satisfiable(And(known_facts_cnf, assumptions, proposition)):
        return False
    if not satisfiable(And(known_facts_cnf, assumptions, Not(proposition))):
        return True
    return None


def register_handler(key, handler):
    """
    Register a handler in the ask system. key must be a string and handler a
    class inheriting from AskHandler::

        >>> from sympy.assumptions import register_handler, ask, Q
        >>> from sympy.assumptions.handlers import AskHandler
        >>> class MersenneHandler(AskHandler):
        ...     # Mersenne numbers are in the form 2**n + 1, n integer
        ...     @staticmethod
        ...     def Integer(expr, assumptions):
        ...         import math
        ...         return ask(Q.integer(math.log(expr + 1, 2)))
        >>> register_handler('mersenne', MersenneHandler)
        >>> ask(Q.mersenne(7))
        True

    """
    if type(key) is Predicate:
        key = key.name
    try:
        getattr(Q, key).add_handler(handler)
    except AttributeError:
        setattr(Q, key, Predicate(key, handlers=[handler]))


def remove_handler(key, handler):
    """Removes a handler from the ask system. Same syntax as register_handler"""
    if type(key) is Predicate:
        key = key.name
    getattr(Q, key).remove_handler(handler)


def single_fact_lookup(known_facts_keys, known_facts_cnf):
    # Compute the quick lookup for single facts
    mapping = {}
    for key in known_facts_keys:
        mapping[key] = set([key])
        for other_key in known_facts_keys:
            if other_key != key:
                if ask_full_inference(other_key, key, known_facts_cnf):
                    mapping[key].add(other_key)
    return mapping


def compute_known_facts(known_facts, known_facts_keys):
    """Compute the various forms of knowledge compilation used by the
    assumptions system.

    This function is typically applied to the variables
    ``known_facts`` and ``known_facts_keys`` defined at the bottom of
    this file.
    """
    from textwrap import dedent, wrap

    fact_string = dedent('''\
    """
    The contents of this file are the return value of
    ``sympy.assumptions.ask.compute_known_facts``.  Do NOT manually
    edit this file.
    """

    from sympy.logic.boolalg import And, Not, Or
    from sympy.assumptions.ask import Q

    # -{ Known facts in CNF }-
    known_facts_cnf = And(
        %s
    )

    # -{ Known facts in compressed sets }-
    known_facts_dict = {
        %s
    }
    ''')
    # Compute the known facts in CNF form for logical inference
    LINE = ",\n    "
    HANG = ' '*8
    cnf = to_cnf(known_facts)
    c = LINE.join([str(a) for a in cnf.args])
    mapping = single_fact_lookup(known_facts_keys, cnf)
    m = LINE.join(['\n'.join(
        wrap("%s: %s" % item,
            subsequent_indent=HANG,
            break_long_words=False))
        for item in mapping.items()])
    return fact_string % (c, m)

# handlers_dict tells us what ask handler we should use
# for a particular key
_val_template = 'sympy.assumptions.handlers.%s'
_handlers = [
    ("antihermitian",     "sets.AskAntiHermitianHandler"),
    ("bounded",           "calculus.AskBoundedHandler"),
    ("commutative",       "AskCommutativeHandler"),
    ("complex",           "sets.AskComplexHandler"),
    ("composite",         "ntheory.AskCompositeHandler"),
    ("even",              "ntheory.AskEvenHandler"),
    ("extended_real",     "sets.AskExtendedRealHandler"),
    ("hermitian",         "sets.AskHermitianHandler"),
    ("imaginary",         "sets.AskImaginaryHandler"),
    ("infinitesimal",     "calculus.AskInfinitesimalHandler"),
    ("integer",           "sets.AskIntegerHandler"),
    ("irrational",        "sets.AskIrrationalHandler"),
    ("rational",          "sets.AskRationalHandler"),
    ("negative",          "order.AskNegativeHandler"),
    ("nonzero",           "order.AskNonZeroHandler"),
    ("positive",          "order.AskPositiveHandler"),
    ("prime",             "ntheory.AskPrimeHandler"),
    ("real",              "sets.AskRealHandler"),
    ("odd",               "ntheory.AskOddHandler"),
    ("algebraic",         "sets.AskAlgebraicHandler"),
    ("is_true",           "TautologicalHandler"),
    ("symmetric",         "matrices.AskSymmetricHandler"),
    ("invertible",        "matrices.AskInvertibleHandler"),
    ("orthogonal",        "matrices.AskOrthogonalHandler"),
    ("positive_definite", "matrices.AskPositiveDefiniteHandler"),
    ("upper_triangular",  "matrices.AskUpperTriangularHandler"),
    ("lower_triangular",  "matrices.AskLowerTriangularHandler"),
    ("diagonal",          "matrices.AskDiagonalHandler"),
]
for name, value in _handlers:
    register_handler(name, _val_template % value)


known_facts_keys = [getattr(Q, attr) for attr in Q.__dict__
                    if not attr.startswith('__')]
known_facts = And(
    Implies(Q.real, Q.complex),
    Implies(Q.real, Q.hermitian),
    Equivalent(Q.even, Q.integer & ~Q.odd),
    Equivalent(Q.extended_real, Q.real | Q.infinity),
    Equivalent(Q.odd, Q.integer & ~Q.even),
    Equivalent(Q.prime, Q.integer & Q.positive & ~Q.composite),
    Implies(Q.integer, Q.rational),
    Implies(Q.imaginary, Q.complex & ~Q.real),
    Implies(Q.imaginary, Q.antihermitian),
    Implies(Q.antihermitian, ~Q.hermitian),
    Equivalent(Q.negative, Q.nonzero & ~Q.positive),
    Equivalent(Q.positive, Q.nonzero & ~Q.negative),
    Equivalent(Q.rational, Q.real & ~Q.irrational),
    Equivalent(Q.real, Q.rational | Q.irrational),
    Implies(Q.nonzero, Q.real),
    Equivalent(Q.nonzero, Q.positive | Q.negative),
    Implies(Q.orthogonal, Q.positive_definite),
    Implies(Q.positive_definite, Q.invertible),
    Implies(Q.diagonal, Q.upper_triangular),
    Implies(Q.diagonal, Q.lower_triangular)
)

from sympy.assumptions.ask_generated import known_facts_dict, known_facts_cnf
