"""Run with python -m unittest discover -s tests (no AstrBot runtime required)."""

import importlib
import json
import sys
import types
import unittest
from pathlib import Path

package = types.ModuleType("onboarding_test_source")
package.__path__ = [str(Path(__file__).resolve().parents[1])]
sys.modules[package.__name__] = package
intent = importlib.import_module(package.__name__ + ".intent_detection")
dialog = importlib.import_module(package.__name__ + ".dialog_context")


class ScopeTests(unittest.TestCase):
    def test_development_and_cosmetic_chat_stays_silent(self):
        for text in (
            "这些文件能不能转换成服务器版本的？",
            "这我用的光影问题吗，为啥月亮是这",
            "就一张正经的服务器地址卡，那你要什么样的图？",
            "这个Forge模组能移植到Fabric服务端吗？",
        ):
            with self.subTest(text=text):
                self.assertTrue(dialog.is_outside_onboarding(text))
                result = intent.parse_answer_result(
                    json.dumps(
                        {
                            "should_reply": True,
                            "confidence": 1,
                            "answer": "请重装整合包",
                            "phrases": [text],
                        }
                    ),
                    text,
                )
                self.assertFalse(result["is_help"])
                self.assertEqual(result["answer"], "")
                self.assertEqual(result["phrases"], [])

    def test_explicit_entry_failure_still_allows_help(self):
        for text in (
            "装了光影后游戏闪退，进不去服务器怎么办？",
            "服务器地址卡的地址连不上，连接失败",
            "适配这个mod后注册表同步失败，实体无法识别",
            "未绑定怎么办",
        ):
            with self.subTest(text=text):
                self.assertFalse(dialog.is_outside_onboarding(text))
                result = intent.parse_answer_result(
                    json.dumps(
                        {
                            "should_reply": True,
                            "confidence": 0.99,
                            "answer": "请提供完整报错",
                            "phrases": [],
                        }
                    ),
                    text,
                )
                self.assertTrue(result["is_help"])


if __name__ == "__main__":
    unittest.main()
