class LibLayeredConfig < Formula
  include Language::Python::Virtualenv

  desc "Layered configuration loader for Python applications"
  homepage "https://github.com/bitranox/lib_layered_config"
  url "https://github.com/bitranox/lib_layered_config/archive/refs/tags/v0.0.1.tar.gz"
  sha256 "<fill-me>"
  license "MIT"

  depends_on "python@3.10"

  resource "rich-click" do
    url "https://files.pythonhosted.org/packages/29/c2/f08b5e7c1a33af8a115be640aa0796ba01c4732696da6d2254391376b314/rich_click-1.9.1.tar.gz"
    sha256 "4f2620589d7287f86265432e6a909de4f281de909fe68d8c835fbba49265d268"
  end

  resource "lib_cli_exit_tools" do
    url "https://files.pythonhosted.org/packages/c0/0a/263aa633ae8926e9c30f28679be58c84691a9e3423863a053aef07d20338/lib_cli_exit_tools-1.3.1.tar.gz"
    sha256 "0d7e496a139748e1f31ac01f55d583169ca8c3dded1830426e926499d1ae560c"
  end

  resource "tomli" do
    url "https://files.pythonhosted.org/packages/18/87/302344fed471e44a87289cf4967697d07e532f2421fdaf868a303cbae4ff/tomli-2.2.1.tar.gz"
    sha256 "cd45e1dc79c835ce60f7404ec8119f2eb06d38b1deba146f07ced3bbc44505ff"
  end

  def install
    virtualenv_install_with_resources
  end

  test do
    output = shell_output("#{bin}/python -c 'import lib_layered_config; print(lib_layered_config.default_env_prefix(\"config-kit\"))'")
    assert_match "CONFIG_KIT", output
  end
end
