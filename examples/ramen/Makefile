# 便捷封装（Windows 上更推荐 .\run.ps1）
# 用法：make BLENDER="/c/Program Files/.../blender.exe" all

BLENDER ?= blender
PYTHON  ?= python
BRIDGE  ?= http://127.0.0.1:8081

.PHONY: all build gen place clean check

all: build gen place

check:
	@curl -s $(BRIDGE)/health | grep -q '"ok": *true' || (echo "bridge not ready: $(BRIDGE)"; exit 2)

build:
	$(BLENDER) -b --factory-startup -P run_build.py

gen: check
	$(PYTHON) gen_props.py

place:
	$(BLENDER) -b stall_base.blend -P run_place.py

clean:
	rm -rf shots glb stall.blend stall.blend1 stall.glb stall_base.blend stall_base.blend1
