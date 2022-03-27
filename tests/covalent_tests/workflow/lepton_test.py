# Copyright 2021 Agnostiq Inc.
#
# This file is part of Covalent.
#
# Licensed under the GNU Affero General Public License 3.0 (the "License").
# A copy of the License may be obtained with this software package or at
#
#      https://www.gnu.org/licenses/agpl-3.0.en.html
#
# Use of this file is prohibited except in compliance with the License. Any
# modifications or derivative works of this file must retain this copyright
# notice, and modified files must contain a notice indicating that they have
# been altered from the originals.
#
# Covalent is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the License for more details.
#
# Relief from the License may be granted by purchasing a commercial license.

"""Unit tests for leptons."""

import inspect
import os
from contextlib import nullcontext

import pytest

from covalent._workflow.electron import Electron
from covalent._workflow.lepton import Lepton


def test_lepton_init(mocker, monkeypatch):
    monkeypatch.setattr(
        "covalent._shared_files.defaults._DEFAULT_CONSTRAINT_VALUES", {"executor": "local"}
    )
    init_mock = mocker.patch("covalent._workflow.lepton.Electron.__init__", return_value=None)
    set_metadata_mock = mocker.patch(
        "covalent._workflow.lepton.Electron.set_metadata", return_value=None
    )
    wrap_mock = mocker.patch(
        "covalent._workflow.lepton.Lepton.wrap_task", return_value="wrapper function"
    )

    lepton = Lepton(
        language="lang",
        library_name="libname",
        function_name="funcname",
        argtypes=[(int, "type")],
    )

    init_mock.assert_called_once_with("wrapper function")
    wrap_mock.assert_called_once_with()
    set_metadata_mock.assert_called_once_with("executor", "local")

    assert lepton.language == "lang"
    assert lepton.library_name == "libname"
    assert lepton.function_name == "funcname"
    assert lepton.argtypes == [("int", "type")]

    assert isinstance(lepton, Electron)


def test_lepton_attributes():
    def filter_attributes(attributes):
        return [a for a in attributes if not (a[0].startswith("__") and a[0].endswith("__"))]

    electron_attributes = filter_attributes(inspect.getmembers(Electron))
    lepton_attributes = filter_attributes(inspect.getmembers(Lepton))

    expected_attributes = [
        ("INPUT", 0),
        ("OUTPUT", 1),
        ("INPUT_OUTPUT", 2),
        ("_LANG_PY", ["Python", "python"]),
        ("_LANG_C", ["C", "c"]),
        ("wrap_task", Lepton.wrap_task),
    ]

    assert sorted(electron_attributes + expected_attributes) == sorted(lepton_attributes)


@pytest.fixture
def init_mock(mocker):
    return mocker.patch("covalent._workflow.lepton.Lepton.__init__", return_value=None)


@pytest.mark.parametrize("language", ["python", "c", "unsupported"])
def test_wrap_task(mocker, init_mock, language):
    lepton = Lepton()
    init_mock.assert_called_once()

    lepton.language = language
    lepton.library_name = "mylib"
    lepton.function_name = "myfunc"

    context = pytest.raises(ValueError) if language == "unsupported" else nullcontext()
    with context:
        task = lepton.wrap_task()

    if language == "unsupported":
        return

    assert task.__code__.co_name == f"{language}_wrapper"
    assert task.__name__ == "myfunc"
    assert task.__qualname__ == "Lepton.mylib.myfunc"
    assert task.__module__ == "covalent._workflow.lepton.mylib"
    assert task.__doc__ == f"Lepton interface for {language} function 'myfunc'."


@pytest.mark.parametrize(
    "library_name,function_name",
    [
        ("test_module", "test_func"),
        ("test_module.py", "test_func"),
        ("bad_module", ""),
        ("bad_module.py", ""),
        ("test_module", "bad_func"),
    ],
)
def test_python_wrapper(mocker, init_mock, library_name, function_name):
    python_test_module_str = """\
def test_func(x, y):
    return x + y\
"""

    with open("test_module.py", "w") as f:
        f.write(python_test_module_str)
        f.flush()

    lepton = Lepton()
    lepton.language = "python"
    lepton.library_name = library_name
    lepton.function_name = function_name
    task = lepton.wrap_task()

    init_mock.assert_called_once_with()

    if library_name.startswith("bad_module"):
        context = pytest.raises((ModuleNotFoundError, FileNotFoundError, AttributeError))
    elif function_name == "bad_func":
        context = pytest.raises(AttributeError)
    else:
        context = nullcontext()

    with context:
        result = task(1, 2)

    os.remove("test_module.py")

    if library_name.startswith("bad_module") or function_name == "bad_func":
        return

    assert result == 3


@pytest.mark.parametrize(
    "library_name,argtypes,args,kwargs",
    [
        ("test_empty.so", [], [], {}),
        ("test_lib.so", [], [], {"bad_kwarg": "bad_value"}),
    ],
)
def test_c_wrapper(mocker, init_mock, library_name, argtypes, args, kwargs):
    lepton = Lepton()
    lepton.language = "C"
    lepton.library_name = library_name
    lepton.function_name = "test_func"
    lepton.argtypes = argtypes
    task = lepton.wrap_task()

    init_mock.assert_called_once_with()

    class MockCCall:
        def __call__(*args, **kwargs):
            return None

    cdll_mock = mocker.patch("ctypes.CDLL", return_value={"test_func": MockCCall})

    if kwargs:
        context = pytest.raises(ValueError)
    else:
        context = nullcontext()

    with context:
        result = task(*args, **kwargs)

    if "bad_kwarg" in kwargs:
        return

    cdll_mock.assert_called_once_with(library_name)

    if library_name == "test_empty.so":
        assert result is None

    # TODO: Still need to test variable translations
