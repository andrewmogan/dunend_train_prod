#!/bin/bash
echo "initiating submodules"
git submodule init

echo "installing larnd-sim"
cd larnd-sim
export SKIP_CUPY_INSTALL=1
pip install . --user
if [ $? -gt 0 ]
then
    echo "Failed to install"
    exit 1
fi
cd ..

echo "installing event parser"
cd larpix_readout_parser
pip install . --user
if [ $? -gt 0 ]
then
    echo "Failed to install larpix_readout_parser"
    exit 1
fi
cd ..

echo "installing SuperaAtomic"
cd SuperaAtomic
export SUPERA_WITHOUT_PYTHON=1
pip install . --user
if [ $? -gt 0 ]
then
    echo "Failed to install SuperaAtomic"
    exit 1
fi
cd ..

echo "installing edep2supera"
cd edep2supera
pip install . --user
if [ $? -gt 0 ]
then
    echo "Failed to install edep2supera"
    exit 1
fi
cd ..

echo "installing larnd2supera"
cd larnd2supera
pip install . --user
if [ $? -gt 0 ]
then
    echo "Failed to install larnd2supera"
    exit 1
fi
cd ..

echo "done"
