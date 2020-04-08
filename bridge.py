from collections import OrderedDict
from math import sqrt, sin, cos, tan, atan, pi, floor

import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['SimHei'] #用来正常显示中文标签
plt.rcParams['axes.unicode_minus']=False #用来正常显示负号
#有中文出现的情况，需要u'内容'

import numpy as np
np.set_printoptions(precision=3, suppress=True)

from utils import partition_kij, update_K, reshape_K, reduce_K, pretty_print




######################################
#                                    #
#               节点类                #
#                                    #
######################################

class Node:
    '''杆件单元节点类'''
    
    def __init__(self, num):
        self.num = num
        self.coordinates = (None, None)
        self.vdisps = []
        
    def __repr__(self):
        return 'Node(%d)' % (self.num)


    

    
######################################
#                                    #
#               杆件单元类             #
#                                    #
######################################    
class Unit:
    '''杆件单元类'''
    def __init__(self, num, nodes_pair):
        self.num             =    num
        self.nodes_pair      =    nodes_pair
        self.node_i          =    self.nodes_pair[0]
        self.node_j          =    self.nodes_pair[1]
        
        # 梁截面数据([梁高 翼缘厚度 腹板厚度 翼缘宽度])
        self.beam_section_data = []           
        
        self._alpha   =   None
        self._length  =   None
        self._area    =   None
        self._E       =   None
        self._kij     =   None
        
        self.axial_forces = []

        
    @property
    def alpha(self):
        if self._alpha:
            return self._alpha
        
        i, j = self.node_i.num, self.node_j.num
        xi, yi = self.node_i.coordinates
        xj, yj = self.node_j.coordinates
        if xi == xj:
            alpha = pi / 2
        else:
            alpha = atan((yj - yi) / (xj - xi)) 
        
        self._alpha = alpha
        return self._alpha
    
    
    @property
    def length(self):
        if self._length:
            return self._length
        
        i, j = self.node_i.num, self.node_j.num
        xi, yi = self.node_i.coordinates
        xj, yj = self.node_j.coordinates
        
        self._length = sqrt((yj - yi)**2 + (xj - xi)**2)
        return self._length
        
    
    @property
    def area(self):
        '''截面面积'''
        if self._area:
            return self._area
        
        a, b, c, d = self.beam_section_data
        self._area = 2 * b * d + (a - 2 * b) * c 
        return self._area
    
    @property
    def kij(self):
        '''单元刚度矩阵'''
        if self._kij is not None:
            return self._kij
        
        a = self.alpha
        l = self.length       # 单元长度
        M = np.array(
        [[cos(a)**2, cos(a)*sin(a), -cos(a)**2, -cos(a)*sin(a)],
        [cos(a)*sin(a), sin(a)**2, -cos(a)*sin(a), -sin(a)**2],
        [-cos(a)**2, -cos(a)*sin(a), cos(a)**2, cos(a)*sin(a)],
        [-cos(a)*sin(a), -sin(a)**2, cos(a)*sin(a), sin(a)**2]])
        
        A = self.area
        E = self._E
        
        self._kij = E * A / l * M

        return self._kij
        
    
    def __repr__(self):
        return 'Unit(%d, (%d, %d))' % (self.num, self.nodes_pair[0].num, self.nodes_pair[1].num)
    


######################################
#                                    #
#               桥类                  #
#                                    #
######################################

class Bridge:
    
    def __init__(self):
        self.nodes      =    OrderedDict()   # {node_num: node}  
        self.units      =    OrderedDict()   # {unit_num: unit}
        self._length    =    None            # 长度/米
        self._K         =    None
        self._reduced_K =    None
        self._n_nodes   =    None
        self._E         =    None
       
        
####################### 读入数据 #####################
    def load_nodes_coordinates(self, path):
        ''' 读入节点坐标数据 '''
        
        file_path = path + 'nodes_coordinates_' + str(self.length) + '.txt'
        with open(file_path, 'r') as nodes_coordinates_file:
            for line in nodes_coordinates_file.readlines():
                node_num, x, y = [int(string) for string in line.strip().split()]
                node = Node(node_num)
                node.coordinates = (x, y)
                self.nodes[node_num] = node
                
    def load_units_data(self, path):
        '''读入杆件数据'''
        
        # 读入单元编号对应杆件编号对
        file_path = path + 'unit_node_mapping_' + str(self.length) + '.txt'
        with open(file_path, 'r') as unit_nodes_mapping_file:
            for line in unit_nodes_mapping_file.readlines():
                unit_num, i, j = [int(string) for string in line.strip().split()]
                node_i, node_j = self.nodes[i], self.nodes[j]
                nodes_pair = (node_i, node_j)
                unit = Unit(unit_num, nodes_pair)
                self.units[unit_num] = unit
        
        # 读入梁截面数据
        file_path = path + 'beam_section_data_' + str(self.length) + '.txt'
        with open(file_path, 'r') as beam_section_data_file:
            for line in beam_section_data_file.readlines():
                # 单元编号 梁高 翼缘厚度 腹板厚度 翼缘宽度
                beam_section_data = line.strip().split()
                self.units[int(beam_section_data[0])].beam_section_data = [float(string) for string in beam_section_data[1:]]

                
    def load_data(self, path):
        
        self.__init__()
        
        self.load_nodes_coordinates(path)
        self.load_units_data(path)
        
        
    def load_params(self, **kargs):
        '''载入参数
            E - 杨氏模量 (Pa)
            P - 外力    (kN)
            h - 恒载    (kN)
            
        '''
        self._E = kargs['E']
        for unit_num, unit in self.units.items():
            unit._E = self._E
        
        self.P = kargs['P']
        self.h = kargs['h']
        
       
        self.bottom_chord_nodes_nums = kargs['bottom_chord_nodes_nums']
        self.bottom_chord_nodes_indices = list(range(len(self.bottom_chord_nodes_nums)))
                  



#################### 属性 ########################

    @property
    def length(self):
        '''桥长度'''
        return self._length
        
       
    
    @property
    def n_nodes(self):
        '''结点个数'''
        if self._n_nodes:
            return self._n_nodes
        
        self._n_nodes = len(self.nodes.keys())
        return self._n_nodes
        
    
    @property
    def K(self):
        '''总体刚度矩阵'''
        if self._K is not None:
            return self._K
        
        K = np.zeros((self.n, self.n, 2, 2))
        for unit_num, unit in self.units.items():
            K = update_K(K, unit, unit.kij)
            
        self._K = reshape_K(K, self.n)
        return self._K
    
    @property
    def reduced_K(self):
        if self._reduced_K is not None:
            return self._reduced_K
        self._reduced_K = reduce_K(self.K, self.length)
        return self._reduced_K
    

    


######################## 计算节点竖向位移 ####################

    def save_nodes_vdisps_moment(self, nodes_vdisps_moment):
        '''将[某一]时刻[所有]节点的竖向位移保存到各个节点的竖向位移向量中'''
        
        raise NotImplementedError
    
    
    def get_nodes_vdisps_moment_on_nodes(self, point):
        '''计算力移动过程中，[某一]时刻力作用在[节点上][所有]节点的竖向位移'''
        
        raise NotImplementedError
    
    
    def get_nodes_vdisps_moment_between_nodes(self, point):
        '''计算力移动过程中，[某一]时刻力作用在[节点间][所有]节点的竖向位移'''
        
        raise NotImplementedError
    
    
    
    def get_nodes_vdisps_moment(self, point):
        '''计算力移动过程中，[某一]时刻[所有]节点的竖向位移'''
        '''
        bc_indices   0                         1                           2   ...    7                             8
        bc_nodes     1                         3                           5   ...   15                            16
        bc_axis     0.0 0.1 0.2 ...  7.8 7.9  8.0 8.1 8.2 ...  15.8 15.9 16.0  ...  56.0 56.1 56.2 ... 63.8 63.9  64.0
        '''
        
        #bc_nodes_nums = self.bottom_chord_nodes_nums
        bc_nodes_indices = self.bottom_chord_nodes_indices
        
        # 力作用在节点上
        bc_nodes_corr_force_disps = [8.0 * bc_node_index for bc_node_index in bc_nodes_indices]  # 力作用在下弦杆某一节点时对应的位移
        if int(point) == point and point in bc_nodes_corr_force_disps:
            D = self.get_nodes_vdisps_moment_on_nodes(point)

        # 力作用在节点间
        else:
            D = self.get_nodes_vdisps_moment_between_nodes(point)

        nodes_vdisps_moment = D
        return nodes_vdisps_moment
    
    
    def nodes_vdisps_init(self):
        for node in self.nodes.values():
            node.vdisps.clear()
    
    
    def get_nodes_vdisps(self):
        '''计算力移动过程中，所有时刻所有节点的竖向位移'''
        '''
        bc_indices  0   1   2   3   4   5   6   7   8
        bc_nodes    1   3   5   7   9  11  13  15  16
        bc_axis     0   8  16  24  32  40  48  56  64
        '''
        
        self.nodes_vdisps_init()
        
        #bc_nodes_nums = self.bottom_chord_nodes_nums
        bc_nodes_indices = self.bottom_chord_nodes_indices
        start, end = 0, (len(bc_nodes_indices) - 1) * 8
        bc_axis = np.arange(start, end + 0.1, step=0.1)
        
        
        # 力在下弦杆移动
        for point in bc_axis:
            nodes_vdisps_moment = self.get_nodes_vdisps_moment(point)
            self.save_nodes_vdisps_moment(nodes_vdisps_moment)
     
        print('Vertical displacements of all nodes saved.')
    
    def show_nodes_vdisps(self):
        '''节点竖向位移影响线'''
        for node in self.nodes.values():
            x = np.arange(0, self.length + 0.1, 0.1)
            y = np.array(node.vdisps)
            plt.plot(x, y)
            plt.xlabel(u'单位力位移')
            plt.ylabel(u'节点竖向位移')
            plt.title(u'节点 ' + str(node.num) + u' 影响线')
            #plt.title('V' + str(node))
            #plt.savefig('/Users/nerd/Desktop/figs/%s.png' % ('V' + str(node)))
            plt.show()

            
            

############## 计算杆件单元轴力 #################

    def units_axial_forces_init(self):
        for unit in self.units.values():
            unit.axial_forces.clear()

            
    def save_units_axial_forces_moment(self, units_axial_forces_moment):
        for unit, one_unit_axial_force_moment in zip(self.units.values(), units_axial_forces_moment):
            unit.axial_forces.append(one_unit_axial_force_moment)

            
    def get_one_unit_axial_force_moment(self, unit, nodes_vdisps_moment):
        '''计算某一时刻某一杆件单元的轴力'''
        
        raise NotImplementedError
    
    
    def get_units_axial_forces_moment(self, point):
        '''计算力移动过程中，某一时刻所有杆件单元的轴力'''
        
        nodes_vdisps_moment = self.get_nodes_vdisps_moment(point)
        units_axial_forces_moment = []
        for unit in self.units.values():
            one_unit_axial_force_moment = self.get_one_unit_axial_force_moment(unit, nodes_vdisps_moment)
            units_axial_forces_moment.append(one_unit_axial_force_moment)   # 需检查和self.units顺序是否对应
            
        return units_axial_forces_moment
    
    
    def get_units_axial_forces(self):
        '''计算力移动过程中，所有时刻所有杆件单元的轴力'''
        '''
        bc_indices  0   1   2   3   4   5   6   7   8
        bc_nodes    1   3   5   7   9  11  13  15  16
        bc_axis     0   8  16  24  32  40  48  56  64
        '''
        
        self.units_axial_forces_init()
        
        #bc_nodes_nums = self.bottom_chord_nodes_nums
        bc_nodes_indices = self.bottom_chord_nodes_indices
        start, end = 0, (len(bc_nodes_indices) - 1) * 8
        bc_axis = np.arange(start, end + 0.1, step=0.1)
        
        
        # 力在下弦杆移动
        for point in bc_axis:
            units_axial_forces_moment = self.get_units_axial_forces_moment(point)
            self.save_units_axial_forces_moment(units_axial_forces_moment)
    
        print('Axial forces of all units saved.')
    
    
    def show_units_axial_forces(self):
        '''杆件单元轴力影响线'''
        for unit in self.units.values():
            x = np.arange(0, self.length + 0.1, 0.1)
            y = np.array(np.around(unit.axial_forces, 3))
            plt.plot(x, y)
            plt.xlabel(u'单位力位移')
            plt.ylabel(u'杆件轴力')
            plt.title(u'杆件 ' + str(unit.num) + u' 影响线')
            #plt.title('V' + str(node))
            #plt.savefig('/Users/nerd/Desktop/figs/%s.png' % ('V' + str(node)))
            plt.show()

    

    


##################### 计算最不利荷载 #####################

    def get_uniform_load_max_trick(self, unit_axial_forces, load, pos_max, neg_min, half):
        '''只有均布荷载作用'''
        
        data = unit_axial_forces
        
        data = data[::-1] if half == 'right' else data
        pos_data = (data > 0) * data
        neg_data = (data < 0) * data

        pos_sum, neg_sum = 0, 0
        for i in range(641 + 1):
            load_selected = list(reversed(load[:i])) if half == 'right' else load[:i]
            selected = np.hstack((load_selected, np.zeros(641 - i)))

            #print(i, len(selected), len(pos_data))
            pos_sum = (pos_data * selected).sum()
            neg_sum = (neg_data * selected).sum()

            pos_max = max(pos_max, pos_sum)
            neg_min = min(neg_min, neg_sum)

        return pos_max, neg_min

    def get_both_load_max_trick(self, unit_axial_forces, load, pos_max, neg_min, half):
        '''均布和集中荷载一起作用'''
        # 0:640, 1:641, ..., 352:992
        
        data = unit_axial_forces
        
        data = data[::-1] if half == 'right' else data    
        pos_data = (data > 0) * data
        neg_data = (data < 0) * data

        pos_sum, neg_sum = 0, 0
        for i in range(353):
            selected = load[i: i + 641]

            pos_sum = (pos_data * selected).sum()
            neg_sum = (neg_data * selected).sum()
            
            pos_max = max(pos_max, pos_sum)
            neg_min = min(neg_min, neg_sum)
            

        return pos_max, neg_min

    def get_unit_worst_cases_load_trick(self, unit_axial_forces, load, pos_max, neg_min):
        '''计算某个杆件单元最不利荷载'''
        
        pos_max, neg_min = compute_uniform_load_max_trick(data, load, pos_max, neg_min, half='left')
        pos_max, neg_min = compute_both_load_max_trick(data, load, pos_max, neg_min, half='left')
        
        pos_max, neg_min = compute_both_load_max_trick(data, load, pos_max, neg_min, half='right')
        pos_max, neg_min = compute_uniform_load_max_trick(data, load, pos_max, neg_min, half='right')

        return pos_max, neg_min

    def get_unit_worst_cases_load_trick2(self, unit_axial_forces, load, pos_max, neg_min):
        '''计算某个杆件单元最不利荷载'''
        
        data = unit_axial_forces
        for half in ['left', 'right']:
            data = data[::-1] if half == 'right' else data    
            pos_data = (data > 0) * data
            neg_data = (data < 0) * data
            pos_sum, neg_sum = 0, 0
            
            # 只有均布荷载作用
            for i in range(641 + 1):
                load_selected = list(reversed(load[:i])) if half == 'right' else load[:i]
                selected = np.hstack((load_selected, np.zeros(641 - i)))

                #print(i, len(selected), len(pos_data))
                pos_sum = (pos_data * selected).sum()
                neg_sum = (neg_data * selected).sum()

                pos_max = max(pos_max, pos_sum)
                neg_min = min(neg_min, neg_sum)
                
            # 均布和集中荷载一起作用
            for i in range(353):
                selected = load[i: i + 641]

                pos_sum = (pos_data * selected).sum()
                neg_sum = (neg_data * selected).sum()

                pos_max = max(pos_max, pos_sum)
                neg_min = min(neg_min, neg_sum)
                
        return pos_max, neg_min
    
    
    def get_worst_cases_load(self, load):
        '''计算所有杆件单元最不利荷载'''
        for unit in self.units.values():
            unit_axial_forces = np.array(unit.axial_forces)
            load = np.array(load)
            pos_max, neg_min = self.get_unit_worst_cases_load_trick(unit_axial_forces, load, pos_max=-np.inf, neg_min=np.inf)     
            unit.max_force = (pos_max, neg_min)



##########################################

    def __repr__(self):
        units_repr = [str(unit) for unit in self.units.values()]
        return '[' + '\n'.join(units_repr) + ']'
    
    


######################################
#                                    #
#               64m 桥子类            #
#                                    #
######################################

class Bridge_64(Bridge):
    '''
    64米钢桥类（无支座）
    '''
    def __init__(self):
        super(Bridge_64, self).__init__()
        self._length = 64
    
    
################### 计算节点竖向位移 #####################

    def save_nodes_vdisps_moment(self, nodes_vdisps_moment):
        '''将[某一]时刻[所有]节点的竖向位移保存到各个节点的竖向位移向量中'''
        
        bc_nodes_nums = self.bottom_chord_nodes_nums
        #bc_nodes_indices = self.bottom_chord_nodes_indices
        
        for node_num in self.nodes.keys():
            # 第1和16个节点竖向位移不在位移向量D中，为0
            if node_num in [bc_nodes_nums[0], bc_nodes_nums[-1]]:   
                self.nodes[node_num].vdisps.append(0.)
            else:
                # v2, v3, v4, ..., v15 <= 1, 3, 5,  ...,  27
                self.nodes[node_num].vdisps.append(float(nodes_vdisps_moment[2 * (node_num - 1) - 1]))
        
    
    def get_nodes_vdisps_moment_on_nodes(self, point):
        '''计算力移动过程中，[某一]时刻力作用在[节点上][所有]节点的竖向位移'''
        
        bc_nodes_indices = self.bottom_chord_nodes_indices
        current_node_index = int(point // 8)
        if current_node_index in [bc_nodes_indices[0], bc_nodes_indices[-1]]:  # 第1个和最后1个
            D = np.zeros((self.reduced_K.shape[0], 1))             # 取决于reduced_K形状 (29, 29)
        else:
            F = np.zeros((self.reduced_K.shape[0], 1))
            F[4 * (current_node_index + 1) - 5] = - self.P          # y3, y5, y7, y11, ..., y15  <= 3, 7, 11, 15, ..., 27
            D = np.matmul(np.linalg.inv(self.reduced_K), F)
            
        return D
    
    
    def get_nodes_vdisps_moment_between_nodes(self, point):
        '''计算力移动过程中，[某一]时刻力作用在[节点间][所有]节点的竖向位移'''
        
        bc_nodes_indices = self.bottom_chord_nodes_indices
        
        F = np.zeros((self.reduced_K.shape[0], 1))
        prev_node_index = int(point // 8)
        next_node_index = prev_node_index + 1

        prev_node_offset = point - 8 * prev_node_index   # 距离前一个节点的位移偏移量, 每个节点间距离8m
        #print(prev_node_index, next_node_index, prev_node_offset)

        next_node_force = - prev_node_offset / 8  # 由杠杆原理得出作用在下一个节点的力
        prev_node_force = - 1 - next_node_force

        # 以64m桥为例
        # 在节点间(1, 3)时不需要算分摊到节点1上的力，对应索引(0, 1)
        # 在节点间(15, 16)时不需要算分摊到节点16上的力，对应索引(7, 8)
        if prev_node_index != bc_nodes_indices[0]:        
            F[4 * (prev_node_index + 1) - 5] = prev_node_force 
        if prev_node_index != bc_nodes_indices[-2]:
            F[4 * (next_node_index + 1) - 5] = next_node_force

        D = np.matmul(np.linalg.inv(self.reduced_K), F)
        return D


    

################# 计算杆件轴力 ###################  
    def get_one_unit_axial_force_moment(self, unit, nodes_vdisps_moment):
        '''计算某一时刻某一杆件单元的轴力'''
        
        i, j = unit.node_i.num, unit.node_j.num

        def get_u_and_v(node_num, nodes_vdisps_moment):
            '''
            index      0    1   2   3      26   27   28 
            (u1) (v1) [u2  v2  u3  v3 ... u15  v15  u16] (v16) 
            '''
            
            D = nodes_vdisps_moment
            bc_nodes_nums = self.bottom_chord_nodes_nums
            
            assert bc_nodes_nums[0] <= node_num <= bc_nodes_nums[-1]  
            # 第1个节点横向和竖向位移都不在位移向量D中，且为0
            if node_num == bc_nodes_nums[0]:  
                u, v = 0, 0
            
            elif bc_nodes_nums[0] < node_num < bc_nodes_nums[-1]:
                u = float(D[2 * (node_num - 1) - 2])  
                v = float(D[2 * (node_num - 1) - 1])  
            
            
            # 最后1个节点横向位移为位移向量D最后一个元素，竖向位移不在位移向量D中，且为0
            elif node_num == bc_nodes_nums[-1]:
                u, v = 0, 0
            
            return u, v
        
        ui, vi = get_u_and_v(i, nodes_vdisps_moment)
        uj, vj = get_u_and_v(j, nodes_vdisps_moment)
        
        kij = unit.kij
        a = unit.alpha
        dij = np.array([[ui], [vi], [uj], [vj]])

        T = np.array(
            [[cos(a), sin(a), 0, 0],
             [-sin(a), cos(a), 0, 0],
             [0, 0, cos(a), sin(a)],
             [0, 0, -sin(a), cos(a)]])
        
        Fij = np.matmul(T, np.matmul(kij, dij))
        f = sqrt(Fij[0]**2 + Fij[1]**2)           # 轴力大小
        
        if unit in [3, 7, 11, 15, 19, 23, 27]:    # 竖杆
            f = f if Fij[0] > 0 else -f
        else:
            f = -f if Fij[0] > 0 else f

        
        one_unit_axial_force_moment = f
        return one_unit_axial_force_moment



    
######################################
#                                    #
#               160m 桥子类           #
#                                    #
######################################

class Bridge_160(Bridge):
    '''
    160米钢桥类（80米 + 支座 + 80米）
    '''
    def __init__(self):
        super(Bridge_160, self).__init__()
        self._length = 160
        
        
#################### 计算节点竖向位移 ################
    def save_nodes_vdisps_moment(self, nodes_vdisps_moment):
        '''将[某一]时刻[所有]节点的竖向位移保存到各个节点的竖向位移向量中'''
        
        bc_nodes_nums = self.bottom_chord_nodes_nums
        bc_middle_node_num = bc_nodes_nums[len(bc_nodes_nums) // 2]  # 第21个节点
        
        for node_num in self.nodes.keys():
            # 第1、21、80个节点竖向位移不在位移向量D中，为0
            
            if node_num in [bc_nodes_nums[0], bc_middle_node_num, bc_nodes_nums[-1]]:   
                self.nodes[node_num].vdisps.append(0.)
            else:
                # v2, v3, v4, ..., v20 <= 1, 3, 5,  ...,  37
                if node_num < bc_middle_node_num:
                    self.nodes[node_num].vdisps.append(float(nodes_vdisps_moment[2 * node_num - 3]))
                
                # (v21), v22, v23, v24 ..., v79, v(80) <= (), 40, 42, 44  ...,  154, ()
                else:
                    self.nodes[node_num].vdisps.append(float(nodes_vdisps_moment[2 * node_num - 4]))
    
    
    def get_nodes_vdisps_moment_on_nodes(self, point):
        '''计算力移动过程中，[某一]时刻力作用在[节点上][所有]节点的竖向位移'''
        '''
        bc_indices  0   1   2   3   4   5   6   7   8   9  10 ...   19   20 
        bc_nodes    1   3   5   7   9  11  13  15  17  19  21 ...   39   40
        bc_axis     0   8  16  24  32  40  48  56  64  72  80 ...  152  160
        '''
        
        
        bc_middle_node_index = len(self.bottom_chord_nodes_nums) // 2  # 第21个节点
        
        bc_nodes_indices = self.bottom_chord_nodes_indices
        current_node_index = int(point // 8)
        if current_node_index in [bc_nodes_indices[0], bc_middle_node_index, bc_nodes_indices[-1]]:  # 第1、21和最后1个
            D = np.zeros((self.reduced_K.shape[0], 1))             # 取决于reduced_K形状 (76, 76)
        else:
            F = np.zeros((self.reduced_K.shape[0], 1))
            if current_node_index < bc_middle_node_index:
                # y3, y5, y7, y11, ..., y19  <= 3, 7, 11, 15, ..., 35
                F[4 * (current_node_index + 1) - 5] = - self.P
            else:
                # y23, y25, y27, ..., y79  <= 
                F[4 * (current_node_index + 1) - 6] = - self.P
                
            D = np.matmul(np.linalg.inv(self.reduced_K), F)
            
        return D
    
    
    def get_nodes_vdisps_moment_between_nodes(self, point):
        '''计算力移动过程中，[某一]时刻力作用在[节点间][所有]节点的竖向位移'''
        
        bc_nodes_indices = self.bottom_chord_nodes_indices
        bc_middle_node_index = len(self.bottom_chord_nodes_nums) // 2  # 第21个节点
        
        
        prev_node_index = int(point // 8)
        next_node_index = prev_node_index + 1

        prev_node_offset = point - 8 * prev_node_index   # 距离前一个节点的位移偏移量, 每个节点间距离8m
        #print(prev_node_index, next_node_index, prev_node_offset)

        next_node_force = - prev_node_offset / 8  # 由杠杆原理得出作用在下一个节点的力
        prev_node_force = - 1 - next_node_force

        # 以64m桥为例
        # 在节点间(1, 3)时不需要算分摊到节点1上的力，对应索引(0, 1)
        # 在节点间(15, 16)时不需要算分摊到节点16上的力，对应索引(7, 8)
        F = np.zeros((self.reduced_K.shape[0], 1))
        
        # ... 17 v 19   21   23 ...
        if next_node_index <= bc_middle_node_index - 1:
            if prev_node_index == bc_nodes_indices[0]:        
                F[4 * (next_node_index + 1) - 5] = next_node_force
            else:
                F[4 * (prev_node_index + 1) - 5] = prev_node_force
                F[4 * (next_node_index + 1) - 5] = next_node_force
            #else: F = 0
        
        # ... 17  19   21  v  23 ...
        elif prev_node_index >= bc_middle_node_index + 1:
            if next_node_index == bc_nodes_indices[-1]:
                F[4 * (prev_node_index + 1) - 6] = prev_node_force    
            else:
                F[4 * (prev_node_index + 1) - 6] = prev_node_force
                F[4 * (next_node_index + 1) - 6] = next_node_force

        # ... 17  19  v  21    23 ...
        # ... 17  19     21 v  23 ...
        else:
            if next_node_index == 21:
                F[4 * (prev_node_index + 1) - 5] = prev_node_force
            elif prev_node_index == 21:
                F[4 * (next_node_index + 1) - 6] = next_node_force
        
        D = np.matmul(np.linalg.inv(self.reduced_K), F)
        return D


    

    
################# 计算杆件单元轴力 ################    
    def get_one_unit_axial_force_moment(self, unit, nodes_vdisps_moment):
        '''计算某一时刻某一杆件单元的轴力'''
        
        i, j = unit.node_i.num, unit.node_j.num
        
                
        def get_u_and_v(node_num, nodes_vdisps_moment):
            '''
            index      0    1   2   3      36   37   38 (   )   39   40   41  42  43  44 ...   155
            (u1) (v1) [u2  v2  u3  v3 ... u20  v20  u21 (v21)  u22  v22  u23 v23 u24 v24 ...   u80] (v80)
            '''
            
            D = nodes_vdisps_moment
            bc_nodes_nums = self.bottom_chord_nodes_nums
            bc_middle_node_num = bc_nodes_nums[len(bc_nodes_nums) // 2]  # 第21个节点
            
            assert bc_nodes_nums[0] <= node_num <= bc_nodes_nums[-1]  # 1 <= node_num <= 80
            # 第1个节点横向和竖向位移都不在位移向量D中，且为0
            if node_num == bc_nodes_nums[0]:  
                u, v = 0, 0
            
            elif bc_nodes_nums[0] < node_num < bc_middle_node_num:
                u = float(D[2 * (node_num - 1) - 2])  
                v = float(D[2 * (node_num - 1) - 1])  
            
            # 中间节点21横向位移为0，竖向位移不在位移向量D中，且为0
            #  u21, (v21), u22, v22
            #   38,    (),  39,  40
            elif node_num == bc_middle_node_num:      
                u, v = 0, 0                           
            
            elif bc_middle_node_num < node_num < bc_nodes_nums[-1]:
                u = float(D[2 * (node_num - 1) - 3])
                v = float(D[2 * (node_num - 1) - 2])  
            
            # 最后1个节点横向位移为位移向量D最后一个元素，竖向位移不在位移向量D中，且为0
            elif node_num == bc_nodes_nums[-1]:
                u, v = 0, 0
            
            return u, v
        
        ui, vi = get_u_and_v(i, nodes_vdisps_moment)
        uj, vj = get_u_and_v(j, nodes_vdisps_moment) 

        kij = unit.kij
        a = unit.alpha
        dij = np.array([[ui], [vi], [uj], [vj]])

        T = np.array(
            [[cos(a), sin(a), 0, 0],
             [-sin(a), cos(a), 0, 0],
             [0, 0, cos(a), sin(a)],
             [0, 0, -sin(a), cos(a)]])
        
        Fij = np.matmul(T, np.matmul(kij, dij))
        f = sqrt(Fij[0]**2 + Fij[1]**2)           # 轴力大小
        
        shaft_units = list(range(3, 75 + 1, 4)) # 竖杆
        if unit in shaft_units:    # 竖杆
            f = f if Fij[0] > 0 else -f
        else:
            f = -f if Fij[0] > 0 else f

        
        one_unit_axial_force_moment = f
        return one_unit_axial_force_moment

    

    
### 计算下弦杆结点位移 ###
'''
下弦杆共9个节点(1, 3, 5, 7, ... 15, 16)，
对于其中2个节点(1, 16):
因每一时刻节点1和16竖向位移都为0， 所以V1, V16为零向量

对于另外7个节点(3, 5, 7, ..., 15):
第1和第9时刻力作用在节点1和16，每个节点竖向位移为0，
其余时刻分别令7个F中(y3, y5, y7, ... y15)为-P，其余元素为0，
由矩阵方程得到对应9个时刻的9个29维位移向量D，
分别取出9个时刻位移向量D的竖向位移v2, v3, ..., v15得到
7个节点对应9个时刻的竖向位移向量V2, V3, ... V15
'''
'''

                  0   1   2   3   4   5   6   7  ...       27   28
     F  x1  y1  [x2  y2  x3  y3  x4  y4  x5  y5  ... x15  y15  x16] y16

        u1  v1   u2  v2  u3  v3  u4  v4  u5  v5  ... u15  v15  u16  v16 
1    D   0   0  [ 0   0   0   0   0   0   0   0   ...  0    0    0]   0
3    D   0   0  [ 0   #   0   #   0   #   0   #        0    #    0]   0     <=  y3 = -P
5    D   0   0  [ 0   #   0   #   0   #   0   #        0    #    0]   0     <=  y5 = -P
   ...
15   D   0   0  [ 0   #   0   #   0   #   0   #        0    #    0]   0     <=  y15 = -P
16   D   0   0  [ 0   0   0   0   0   0   0   0   ...  0    0    0]   0
            V1       V2      V3      V4      V5           V15       V16   

          y3 = -P  y5 = -P  ... y15 = -P 
V1  [0       0        0     ...     0      0]   9 * 1
V2  [0      v2       v2     ...    v2      0]
...
V15 [0     v15      v15     ...   v15      0]
V16 [0       0        0     ...     0      0]
'''