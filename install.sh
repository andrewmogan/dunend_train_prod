#!/bin/bash
echo "initiating submodules"
git submodule init
git submodule update

echo "installing event parser"
cd modules/larpix_readout_parser
pip install . --user
if [ $? -gt 0 ]
then
    echo "Failed to install larpix_readout_parser"
    exit 1
fi
cd -

echo "installing SuperaAtomic"
cd modules/SuperaAtomic
export SUPERA_WITHOUT_PYTHON=1
pip install . --user
if [ $? -gt 0 ]
then
    echo "Failed to install SuperaAtomic"
    exit 1
fi
cd -

echo "installing edep2supera"
cd modules/edep2supera
pip install . --user
if [ $? -gt 0 ]
then
    echo "Failed to install edep2supera"
    exit 1
fi
cd -

echo "installing larnd2supera"
cd modules/larnd2supera
pip install . --user
if [ $? -gt 0 ]
then
    echo "Failed to install larnd2supera"
    exit 1
fi
cd -

echo "done"
