import unittest

from case1_clearing_turn.models import ClearingTurnState
from case1_clearing_turn.state_machine import StateMachine


class StateMachineTests(unittest.TestCase):
    def test_normal_transition_chain(self):
        machine = StateMachine()
        chain = [
            ClearingTurnState.ARMED, ClearingTurnState.WAIT_LAUNCH, ClearingTurnState.WAIT_SAFE,
            ClearingTurnState.FIRST_TURN, ClearingTurnState.REVERSING,
            ClearingTurnState.BRC_CAPTURE, ClearingTurnState.EXITING, ClearingTurnState.COMPLETED,
        ]
        for index, state in enumerate(chain):
            machine.transition(state, float(index))
        self.assertEqual(machine.state, ClearingTurnState.COMPLETED)

    def test_impossible_transition_rejected(self):
        with self.assertRaises(RuntimeError):
            StateMachine().transition(ClearingTurnState.COMPLETED, 0.0)


if __name__ == "__main__":
    unittest.main()
